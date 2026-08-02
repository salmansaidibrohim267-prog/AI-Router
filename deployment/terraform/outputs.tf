output "ecr_repository_url" {
  description = "ECR repository URL for the AI Router image"
  value       = aws_ecr_repository.ai_router.repository_url
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.ai_router.name
}

output "ecs_service_name" {
  description = "ECS service name"
  value       = aws_ecs_service.ai_router.name
}

output "log_group" {
  description = "CloudWatch log group"
  value       = aws_cloudwatch_log_group.ai_router.name
}
