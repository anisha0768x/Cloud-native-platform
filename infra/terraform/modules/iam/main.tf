# IRSA role for K8s Management Service (Module 6). WHY this needs an IAM
# role at all, when its real work is talking to the KUBERNETES API (not
# AWS APIs): EKS's own API server auth also flows through IAM (the
# aws-auth ConfigMap maps IAM roles to K8s RBAC subjects) — so this role
# is what lets the ServiceAccount authenticate to the K8s API as a
# distinct, narrowly-scoped identity at all, before K8s-native RBAC (a
# Role + RoleBinding, applied separately, not shown here since it's
# cluster-side config Terraform doesn't own) further restricts exactly
# which verbs/resources it can touch (list/watch pods+nodes+deployments,
# patch deployments/scale — matching KubernetesClusterProvider's actual
# API calls, nothing broader).

resource "aws_iam_role" "k8s_management_service" {
  name = "platform-k8s-management-service"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = var.oidc_provider_arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${replace(var.oidc_provider_url, "https://", "")}:sub" = "system:serviceaccount:platform:k8s-management-service"
          "${replace(var.oidc_provider_url, "https://", "")}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

# IRSA role for Cloud Storage Service (Module 12) — real S3 access
# instead of the static access-key/secret-key pair its local-dev
# S3StorageProvider config uses against MinIO. Scoped to exactly the one
# bucket the S3 module creates, not `s3:*` on every bucket in the account.
resource "aws_iam_role" "cloud_storage_service" {
  name = "platform-cloud-storage-service"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = var.oidc_provider_arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${replace(var.oidc_provider_url, "https://", "")}:sub" = "system:serviceaccount:platform:cloud-storage-service"
          "${replace(var.oidc_provider_url, "https://", "")}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "cloud_storage_service_s3" {
  name = "s3-access"
  role = aws_iam_role.cloud_storage_service.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket",
      ]
      Resource = [
        var.storage_bucket_arn,
        "${var.storage_bucket_arn}/*",
      ]
    }]
  })
}
