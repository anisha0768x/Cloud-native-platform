# Terraform root module: AWS infrastructure for the platform.
#
# WHY AWS specifically (not a multi-cloud abstraction): the architecture
# doc's own service choices already assume AWS-shaped primitives (EKS,
# RDS, ElastiCache, MSK, S3) — building a cloud-agnostic abstraction over
# Terraform providers is a well-known anti-pattern (you end up with the
# lowest common denominator of every provider's features, and still leak
# provider-specific details somewhere). If a GCP deployment is ever
# needed, that's a parallel `infra/terraform-gcp/` root, not a shared
# abstraction layer bolted onto this one.

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Remote state in S3 with DynamoDB locking — never local state for
  # anything beyond a solo throwaway experiment; local state has no
  # locking (two people running `apply` simultaneously corrupt each
  # other's changes) and no durability guarantee if a laptop dies.
  backend "s3" {
    bucket         = "platform-terraform-state"    # created out-of-band, once, before first `terraform init`
    key            = "platform/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "platform-terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "cloud-native-platform"
      ManagedBy   = "terraform"
      Environment = var.environment
    }
  }
}

module "vpc" {
  source                  = "./modules/vpc"
  vpc_cidr                = var.vpc_cidr
  availability_zone_count = var.availability_zone_count
}

module "eks" {
  source              = "./modules/eks"
  cluster_version     = var.eks_cluster_version
  vpc_id              = module.vpc.vpc_id
  public_subnet_ids   = module.vpc.public_subnet_ids
  private_subnet_ids  = module.vpc.private_subnet_ids
  node_instance_types = var.eks_node_instance_types
  node_min_size       = var.eks_node_min_size
  node_max_size       = var.eks_node_max_size
}

module "rds" {
  source                      = "./modules/rds"
  vpc_id                      = module.vpc.vpc_id
  private_subnet_ids          = module.vpc.private_subnet_ids
  eks_node_security_group_id  = module.eks.node_security_group_id
  instance_class               = var.rds_instance_class
  allocated_storage_gb         = var.rds_allocated_storage_gb
  environment                  = var.environment
}

module "elasticache" {
  source                      = "./modules/elasticache"
  vpc_id                      = module.vpc.vpc_id
  private_subnet_ids          = module.vpc.private_subnet_ids
  eks_node_security_group_id  = module.eks.node_security_group_id
  node_type                    = var.redis_node_type
  environment                  = var.environment
}

module "msk" {
  source                      = "./modules/msk"
  vpc_id                      = module.vpc.vpc_id
  private_subnet_ids          = module.vpc.private_subnet_ids
  eks_node_security_group_id  = module.eks.node_security_group_id
  instance_type                = var.kafka_instance_type
  broker_count                 = var.kafka_broker_count
}

module "s3" {
  source      = "./modules/s3"
  environment = var.environment
}

module "iam" {
  source              = "./modules/iam"
  oidc_provider_arn   = module.eks.oidc_provider_arn
  oidc_provider_url   = module.eks.oidc_provider_url
  storage_bucket_arn  = module.s3.bucket_arn
}
