# EKS cluster: control plane in AWS-managed subnets (spanning both
# public and private subnets is required by EKS itself), worker nodes in
# private subnets only (per the VPC module's isolation design).
#
# IRSA (IAM Roles for Service Accounts) is provisioned here via the OIDC
# provider — this is WHY K8s Management Service's ServiceAccount in
# services.yaml (see infra/k8s/generate_manifests.py) can call real AWS
# APIs (or in-cluster K8s APIs with proper RBAC) without static,
# long-lived AWS credentials baked into a Secret: the ServiceAccount
# assumes an IAM role scoped to exactly what it needs, nothing more.

# Explicit node security group (rather than relying on AWS's
# auto-created default) — this is the group referenced by name from the
# RDS/ElastiCache/MSK modules' ingress rules, so "which security group
# can reach the database" is an explicit, reviewable Terraform reference
# rather than an implicit AWS-managed group discovered only by reading
# the console.
resource "aws_security_group" "eks_nodes" {
  name_prefix = "platform-eks-nodes-"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "platform-eks-nodes" }
}

resource "aws_iam_role" "eks_cluster" {
  name = "platform-eks-cluster-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "eks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  role       = aws_iam_role.eks_cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

resource "aws_eks_cluster" "main" {
  name     = "platform-cluster"
  role_arn = aws_iam_role.eks_cluster.arn
  version  = var.cluster_version

  vpc_config {
    subnet_ids              = concat(var.public_subnet_ids, var.private_subnet_ids)
    endpoint_private_access = true
    endpoint_public_access  = true # restrict to specific CIDRs (public_access_cidrs) in a real prod deployment
  }

  depends_on = [aws_iam_role_policy_attachment.eks_cluster_policy]
}

# OIDC provider — the mechanism IRSA depends on. Without this, a
# ServiceAccount annotation requesting an IAM role has nothing to trust.
data "tls_certificate" "eks_oidc" {
  url = aws_eks_cluster.main.identity[0].oidc[0].issuer
}

resource "aws_iam_openid_connect_provider" "eks" {
  url             = aws_eks_cluster.main.identity[0].oidc[0].issuer
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.eks_oidc.certificates[0].sha1_fingerprint]
}

resource "aws_iam_role" "eks_node" {
  name = "platform-eks-node-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_node_worker" {
  role       = aws_iam_role.eks_node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}

resource "aws_iam_role_policy_attachment" "eks_node_cni" {
  role       = aws_iam_role.eks_node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

resource "aws_iam_role_policy_attachment" "eks_node_ecr" {
  role       = aws_iam_role.eks_node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# Launch template — the mechanism that actually attaches
# aws_security_group.eks_nodes to node ENIs; a managed node group alone
# has no `vpc_security_group_ids` argument of its own (a real provider
# constraint, not a stylistic choice), so the security group must be
# threaded through a launch template instead.
resource "aws_launch_template" "eks_nodes" {
  name_prefix            = "platform-eks-node-"
  vpc_security_group_ids = [aws_security_group.eks_nodes.id]

  tag_specifications {
    resource_type = "instance"
    tags          = { Name = "platform-eks-node" }
  }
}

# ONE general-purpose node group. WHY not split general/compute pools
# (as the master architecture doc's §8 mentions as an option): this
# platform's heaviest CPU consumers (Traffic Prediction / Predictive
# Maintenance training) run in-process within an already-deployed
# service pod, not as separate batch Jobs that would benefit from a
# tainted, isolated node pool — that split earns its complexity only once
# training becomes a scheduled Job workload, which it isn't yet (Module
# 8/9 train lazily on request, see their READMEs).
resource "aws_eks_node_group" "general" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "general"
  node_role_arn   = aws_iam_role.eks_node.arn
  subnet_ids      = var.private_subnet_ids

  instance_types = var.node_instance_types

  launch_template {
    id      = aws_launch_template.eks_nodes.id
    version = aws_launch_template.eks_nodes.latest_version
  }

  scaling_config {
    min_size     = var.node_min_size
    max_size     = var.node_max_size
    desired_size = var.node_min_size
  }

  update_config {
    max_unavailable = 1
  }

  depends_on = [
    aws_iam_role_policy_attachment.eks_node_worker,
    aws_iam_role_policy_attachment.eks_node_cni,
    aws_iam_role_policy_attachment.eks_node_ecr,
  ]
}
