resource "aws_db_subnet_group" "chirp" {
  name       = "${local.project}-${local.environment}"
  subnet_ids = module.vpc.private_subnets

  tags = {
    Project     = local.project
    Environment = local.environment
  }
}

resource "aws_security_group" "rds" {
  name_prefix = "${local.project}-${local.environment}-rds-"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
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
    Name        = "${local.project}-rds-sg"
    Project     = local.project
    Environment = local.environment
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_db_instance" "chirp" {
  identifier = "${local.project}-${local.environment}"

  engine               = "postgres"
  engine_version       = "16.4"
  instance_class       = "db.t3.micro"
  allocated_storage    = 20
  max_allocated_storage = 100

  db_name  = "postgres"
  username = "chirp_admin"
  password = var.db_password

  multi_az               = true
  db_subnet_group_name   = aws_db_subnet_group.chirp.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  publicly_accessible = false

  backup_retention_period = 1
  backup_window          = "03:00-04:00"
  maintenance_window     = "Mon:04:00-Mon:05:00"

  performance_insights_enabled = true

  deletion_protection = true
  skip_final_snapshot = false
  final_snapshot_identifier = "${local.project}-${local.environment}-final"

  tags = {
    Name        = "${local.project}-${local.environment}"
    Project     = local.project
    Environment = local.environment
  }
}

provider "postgresql" {
  host     = aws_db_instance.chirp.address
  port     = aws_db_instance.chirp.port
  username = "chirp_admin"
  password = var.db_password
  sslmode  = "require"
}

resource "postgresql_database" "service_dbs" {
  for_each = toset([
    "chirp_auth",
    "chirp_user",
    "chirp_post",
    "chirp_graph",
    "chirp_timeline",
    "chirp_search",
    "chirp_notification",
    "chirp_messaging",
    "chirp_media",
    "chirp_moderation",
  ])

  name       = each.key
  encoding   = "UTF8"

  depends_on = [aws_db_instance.chirp]
}
