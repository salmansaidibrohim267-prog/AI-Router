variable "region" {
  description = "AWS region"
  type        = string
  default     = "eu-west-1"
}

variable "desired_count" {
  description = "Number of ECS tasks"
  type        = number
  default     = 2
}

variable "image_uri" {
  description = "AI Router container image URI (immutable tag)"
  type        = string
  default     = "ghcr.io/salmansaidibrohim267-prog/AI-Router:1.0.0-rc.1"
}

variable "log_level" {
  description = "Application log level"
  type        = string
  default     = "INFO"
}

variable "config_bucket_arn" {
  description = "ARN of the S3 bucket holding runtime config"
  type        = string
}

variable "execution_role_arn" {
  description = "ARN of the ECS execution role"
  type        = string
}

variable "private_subnets" {
  description = "Subnet IDs for Fargate tasks"
  type        = list(string)
}

variable "ecs_security_group_id" {
  description = "Security group for ECS tasks"
  type        = string
}

variable "alb_target_group_arn" {
  description = "ALB target group ARN"
  type        = string
}
