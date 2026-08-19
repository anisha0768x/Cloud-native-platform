output "k8s_management_service_role_arn" {
  value = aws_iam_role.k8s_management_service.arn
}

output "cloud_storage_service_role_arn" {
  value = aws_iam_role.cloud_storage_service.arn
}
