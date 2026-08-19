variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod) — must match the K8s overlay being deployed"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zone_count" {
  description = "Number of AZs to spread subnets across (min 2 for RDS Multi-AZ / EKS control plane requirements)"
  type        = number
  default     = 3
}

variable "eks_cluster_version" {
  description = "Kubernetes version for the EKS control plane"
  type        = string
  default     = "1.30"
}

variable "eks_node_instance_types" {
  description = "Instance types for the general-purpose EKS node group"
  type        = list(string)
  default     = ["t3.large"]
}

variable "eks_node_min_size" {
  type    = number
  default = 3
}

variable "eks_node_max_size" {
  type    = number
  default = 10
}

variable "rds_instance_class" {
  description = "RDS instance class — hosts ALL 8 service databases (see infra/postgres-init/), not one per service, matching the local-dev docker-compose pattern"
  type        = string
  default     = "db.t3.medium"
}

variable "rds_allocated_storage_gb" {
  type    = number
  default = 100
}

variable "redis_node_type" {
  type    = string
  default = "cache.t3.medium"
}

variable "kafka_instance_type" {
  type    = string
  default = "kafka.t3.small"
}

variable "kafka_broker_count" {
  description = "Must be a multiple of the number of AZs for even distribution"
  type        = number
  default     = 3
}
