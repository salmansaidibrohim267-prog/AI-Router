# Terraform module skeleton for AI Router infrastructure.
# Plan: terraform plan -var-file=production.tfvars
# Apply: terraform apply -auto-approve

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  backend "s3" {
    bucket         = "ai-router-terraform-state"
    key            = "production/terraform.tfstate"
    region         = "eu-west-1"
    dynamodb_table = "ai-router-terraform-locks"
  }
}

provider "aws" {
  region = var.region
}

resource "aws_ecr_repository" "ai_router" {
  name                 = "ai-router"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
  encryption_configuration {
    encryption_type = "KMS"
  }
  tags = {
    Name    = "ai-router"
    Managed = "terraform"
  }
}

resource "aws_ecr_lifecycle_policy" "ai_router" {
  repository = aws_ecr_repository.ai_router.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Retain all release-tagged images"
        selection = {
          tagStatus   = "tagged"
          tagPrefixList = ["v"]
          countType   = "imageCountMoreThan"
          countNumber = 100
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Expire untagged images after 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = { type = "expire" }
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "ai_router" {
  name              = "/ai-router/production"
  retention_in_days = 30
  tags = {
    Name = "ai-router"
  }
}

resource "aws_iam_role" "ai_router_task" {
  name = "ai-router-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = { Service = "ecs-tasks.amazonaws.com" }
      }
    ]
  })
}

resource "aws_iam_role_policy" "ai_router_task_policy" {
  name = "ai-router-task-policy"
  role = aws_iam_role.ai_router_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.ai_router.arn}:*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = var.config_bucket_arn
      }
    ]
  })
}

resource "aws_ecs_cluster" "ai_router" {
  name = "ai-router-production"
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_service" "ai_router" {
  name            = "ai-router"
  cluster         = aws_ecs_cluster.ai_router.id
  task_definition = aws_ecs_task_definition.ai_router.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnets
    security_groups  = [var.ecs_security_group_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = var.alb_target_group_arn
    container_name   = "ai-router"
    container_port   = 8000
  }

  health_check_grace_period_seconds = 60

  deployment_controller {
    type = "ECS"
  }
}

resource "aws_ecs_task_definition" "ai_router" {
  family                   = "ai-router"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = aws_iam_role.ai_router_task.arn
  container_definitions = jsonencode([
    {
      name      = "ai-router"
      image     = var.image_uri
      essential = true
      portMappings = [{ containerPort = 8000, protocol = "tcp" }]
      environment = [
        { name = "LOG_LEVEL", value = var.log_level }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ai_router.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "ai-router"
        }
      }
    }
  ])

  tags = {
    Name = "ai-router"
  }
}
