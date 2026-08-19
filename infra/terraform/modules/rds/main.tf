# RDS PostgreSQL: ONE instance, hosting all 8 services' separate
# databases (auth_service, monitoring_service, metrics_service, etc.) —
# matching infra/postgres-init/01-create-service-databases.sql's local-dev
# pattern exactly, so the same bounded-context isolation (separate
# databases, not schemas) holds in production too, just without needing 8
# separate RDS instances' worth of fixed cost. Splitting to per-service
# RDS instances is a legitimate scale-up path once any one service's load
# actually justifies its own instance — not a default to start from.
#
# Metrics Service (Module 5) specifically wants TimescaleDB — RDS doesn't
# support that extension; Amazon's answer is Aurora PostgreSQL with the
# equivalent Timescale-compatible extension unavailable, so a real
# deployment either self-hosts Timescale on EC2/EKS for that one
# database, or (more commonly today) uses Amazon Timestream / a separate
# managed Timescale Cloud instance for JUST metrics-service's database.
# Not modeled as a separate resource here to keep this module's scope to
# what's actually been built and tested (Modules 1-14); noted as the
# concrete next step if Metrics Service's real-TimescaleDB path (see its
# migration's graceful-fallback logic, Module 5) is ever exercised for
# real.

resource "aws_db_subnet_group" "main" {
  name       = "platform-db-subnet-group"
  subnet_ids = var.private_subnet_ids
}

resource "aws_security_group" "rds" {
  name_prefix = "platform-rds-"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Postgres from EKS nodes only"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.eks_node_security_group_id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "random_password" "db_master" {
  length  = 32
  special = false # avoid characters that need URL-encoding in DATABASE_URL connection strings
}

# The generated password is written to Secrets Manager, never to
# Terraform output/state in plaintext-readable form beyond what state
# encryption already covers — External Secrets Operator (see
# infra/k8s/base/secrets-template.yaml) syncs it into each service's K8s
# Secret from here, not the other way around.
resource "aws_secretsmanager_secret" "db_master_password" {
  name = "platform/rds/master-password"
}

resource "aws_secretsmanager_secret_version" "db_master_password" {
  secret_id     = aws_secretsmanager_secret.db_master_password.id
  secret_string = random_password.db_master.result
}

resource "aws_db_instance" "main" {
  identifier     = "platform-postgres"
  engine         = "postgres"
  engine_version = "16"
  instance_class = var.instance_class

  allocated_storage     = var.allocated_storage_gb
  max_allocated_storage = var.allocated_storage_gb * 2 # storage autoscaling ceiling
  storage_encrypted     = true

  db_name  = "platform"
  username = "platform"
  password = random_password.db_master.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  multi_az                = var.environment == "prod"
  backup_retention_period = var.environment == "prod" ? 7 : 1
  skip_final_snapshot     = var.environment != "prod"
  deletion_protection     = var.environment == "prod"

  tags = { Name = "platform-postgres" }
}
