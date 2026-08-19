output "eks_cluster_name" {
  value = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "configure_kubectl" {
  description = "Run this after `terraform apply` to point kubectl at the new cluster"
  value       = "aws eks update-kubeconfig --region ${var.aws_region} --name ${module.eks.cluster_name}"
}

output "rds_endpoint" {
  value     = module.rds.endpoint
  sensitive = true
}

output "redis_endpoint" {
  value = module.elasticache.primary_endpoint
}

output "kafka_bootstrap_brokers" {
  value = module.msk.bootstrap_brokers_tls
}

output "storage_bucket_name" {
  value = module.s3.bucket_name
}

output "k8s_management_service_role_arn" {
  description = "Annotate the k8s-management-service ServiceAccount with this ARN for IRSA"
  value       = module.iam.k8s_management_service_role_arn
}

output "cloud_storage_service_role_arn" {
  description = "Annotate the cloud-storage-service ServiceAccount with this ARN for IRSA"
  value       = module.iam.cloud_storage_service_role_arn
}
