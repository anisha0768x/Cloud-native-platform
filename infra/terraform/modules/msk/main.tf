# MSK (managed Kafka): backs Metrics Service's primary ingestion path
# (Module 5) and GenAI Log Analysis Service's log ingestion (Module 10) —
# the two consumers already built against platform_common's
# EventProducer/EventConsumer (Module 1), which speak plain Kafka
# protocol and need zero code changes to point at MSK instead of the
# local docker-compose Kafka container.

resource "aws_security_group" "msk" {
  name_prefix = "platform-msk-"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Kafka broker traffic from EKS nodes only"
    from_port       = 9092
    to_port         = 9098 # covers plaintext, TLS, and SASL listener ports MSK exposes
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

resource "aws_msk_cluster" "main" {
  cluster_name           = "platform-kafka"
  kafka_version          = "3.6.0"
  number_of_broker_nodes = var.broker_count

  broker_node_group_info {
    instance_type   = var.instance_type
    client_subnets  = var.private_subnet_ids
    security_groups = [aws_security_group.msk.id]

    storage_info {
      ebs_storage_info {
        volume_size = 100
      }
    }
  }

  encryption_info {
    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
  }
}
