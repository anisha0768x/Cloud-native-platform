# S3 bucket backing Cloud Storage Service (Module 12). Its S3StorageProvider
# already targets any S3-compatible endpoint via S3_ENDPOINT_URL (MinIO
# locally, unset here for real AWS S3) — this module is the "unset"
# side, no application code changes needed to point at it.

resource "aws_s3_bucket" "storage" {
  bucket = "platform-storage-${var.environment}" # environment-suffixed: dev/staging/prod must never share a bucket
}

resource "aws_s3_bucket_versioning" "storage" {
  bucket = aws_s3_bucket.storage.id
  versioning_configuration {
    status = "Enabled" # protects log archives/reports from accidental overwrite or delete
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "storage" {
  bucket = aws_s3_bucket.storage.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "storage" {
  bucket                  = aws_s3_bucket.storage.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Lifecycle rule matching the master architecture doc's §6.3 log-retention
# design (hot -> warm -> archived) — applied here to whatever Cloud
# Storage Service writes under `logs/`, complementing (not duplicating)
# OpenSearch's own ILM policy for actively-searchable logs.
resource "aws_s3_bucket_lifecycle_configuration" "storage" {
  bucket = aws_s3_bucket.storage.id

  rule {
    id     = "archive-old-logs"
    status = "Enabled"
    filter {
      prefix = "logs/"
    }
    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
    transition {
      days          = 90
      storage_class = "GLACIER"
    }
  }
}
