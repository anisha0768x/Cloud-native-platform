output "bootstrap_brokers_tls" {
  value = aws_msk_cluster.main.bootstrap_brokers_tls
}

output "security_group_id" {
  value = aws_security_group.msk.id
}
