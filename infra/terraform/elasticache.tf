resource "aws_elasticache_subnet_group" "chirp" {
  name       = "${local.project}-${local.environment}"
  subnet_ids = module.vpc.private_subnets

  tags = {
    Project     = local.project
    Environment = local.environment
  }
}

resource "aws_security_group" "redis" {
  name_prefix = "${local.project}-${local.environment}-redis-"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${local.project}-redis-sg"
    Project     = local.project
    Environment = local.environment
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_elasticache_replication_group" "chirp" {
  replication_group_id = "${local.project}-${local.environment}"
  description          = "Redis cluster for ${local.project} cache and event bus"

  node_type            = var.redis_node_type
  num_cache_clusters   = var.redis_num_nodes

  engine               = "redis"
  engine_version       = "7.0"
  port                 = 6379

  automatic_failover_enabled = false
  multi_az_enabled          = false

  at_rest_encryption_enabled = true
  transit_encryption_enabled = length(var.redis_password) > 0
  auth_token                = length(var.redis_password) > 0 ? var.redis_password : null

  snapshot_retention_limit = 7
  snapshot_window         = "04:00-06:00"
  maintenance_window      = "sun:06:00-sun:07:00"

  subnet_group_name  = aws_elasticache_subnet_group.chirp.name
  security_group_ids = [aws_security_group.redis.id]

  tags = {
    Name        = "${local.project}-${local.environment}"
    Project     = local.project
    Environment = local.environment
  }
}
