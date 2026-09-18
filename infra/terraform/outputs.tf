output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "private_subnets" {
  description = "Private subnet IDs"
  value       = module.vpc.private_subnets
}

output "public_subnets" {
  description = "Public subnet IDs"
  value       = module.vpc.public_subnets
}

output "eks_cluster_name" {
  description = "EKS cluster name (use with: aws eks update-kubeconfig --name <name>)"
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "EKS cluster API endpoint"
  value       = module.eks.cluster_endpoint
}

output "eks_cluster_certificate_authority" {
  description = "Base64-encoded CA certificate for kubectl"
  value       = module.eks.cluster_certificate_authority_data
  sensitive   = true
}

output "eks_node_security_group_id" {
  description = "Security group ID of EKS nodes (used by RDS/Redis ingress rules)"
  value       = module.eks.node_security_group_id
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint (host:port)"
  value       = aws_db_instance.chirp.endpoint
}

output "rds_host" {
  description = "RDS PostgreSQL host"
  value       = aws_db_instance.chirp.address
}

output "rds_port" {
  description = "RDS PostgreSQL port"
  value       = aws_db_instance.chirp.port
}

output "rds_databases" {
  description = "List of service databases created"
  value       = [for db in postgresql_database.service_dbs : db.name]
}

output "redis_endpoint" {
  description = "Redis primary endpoint"
  value       = aws_elasticache_replication_group.chirp.primary_endpoint_address
}

output "redis_port" {
  description = "Redis port"
  value       = aws_elasticache_replication_group.chirp.port
}

output "s3_media_bucket" {
  description = "S3 bucket name for media storage"
  value       = aws_s3_bucket.media.id
}

output "s3_frontend_bucket" {
  description = "S3 bucket name for frontend"
  value       = aws_s3_bucket.frontend.id
}

output "cloudfront_domain" {
  description = "CloudFront distribution domain name (use for DNS CNAME)"
  value       = aws_cloudfront_distribution.frontend.domain_name
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID (for cache invalidation)"
  value       = aws_cloudfront_distribution.frontend.id
}

output "ecr_repository_url" {
  description = "ECR repository URL (push images here)"
  value       = aws_ecr_repository.services.repository_url
}

output "database_urls" {
  description = "DATABASE_URL for each service"
  sensitive   = true
  value = {
    for name, db in postgresql_database.service_dbs :
    name => "postgresql+asyncpg://chirp_admin:${var.db_password}@${aws_db_instance.chirp.address}:${aws_db_instance.chirp.port}/${db.name}"
  }
}
