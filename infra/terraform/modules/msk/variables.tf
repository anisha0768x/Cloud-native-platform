variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "eks_node_security_group_id" {
  type = string
}

variable "instance_type" {
  type = string
}

variable "broker_count" {
  type = number
}
