# ElastiCache Redis: backs Dashboard Service's cache (Module 7),
# API Gateway's rate limiter (Module 3), and GenAI Log Analysis Service's
# analysis-dedup cache (Module 10) — one cluster, DB-index-separated per
# consumer (matching how local dev's docker-compose Redis is used: one
# container, `redis://.../0`, `.../1` etc. per service).

resource "aws_elasticache_subnet_group" "main" {
  name       = "platform-redis-subnet-group"
  subnet_ids = var.private_subnet_ids
}

resource "aws_security_group" "redis" {
  name_prefix = "platform-redis-"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Redis from EKS nodes only"
    from_port       = 6379
    to_port         = 6379
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

resource "aws_elasticache_replication_group" "main" {
  replication_group_id = "platform-redis"
  description           = "Shared cache/rate-limit/dedup store for the platform"

  engine         = "redis"
  engine_version = "7.1"
  node_type      = var.node_type

  num_cache_clusters = var.environment == "prod" ? 2 : 1 # primary + 1 replica in prod for automatic failover

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.redis.id]

  automatic_failover_enabled = var.environment == "prod"
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
}
