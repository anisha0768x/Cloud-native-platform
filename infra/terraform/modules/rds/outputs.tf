output "endpoint" {
  value = aws_db_instance.main.endpoint
}

output "security_group_id" {
  value = aws_security_group.rds.id
}

output "master_password_secret_arn" {
  value = aws_secretsmanager_secret.db_master_password.arn
}
