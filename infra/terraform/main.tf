terraform {
  required_version = ">= 1.6"
  required_providers { aws = { source = "hashicorp/aws", version = "~> 5.0" } }
}
provider "aws" { region = var.aws_region }

# Production expansion point: place EKS, RDS PostgreSQL, ElastiCache, MSK and
# S3 resources in separate reviewed modules before any apply. No cloud resource
# is created merely by checking this repository out.
