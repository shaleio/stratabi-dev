terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }

    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

# ============================================================================
# StrataBI — Developer / Community Edition data plane
# ----------------------------------------------------------------------------
# This stack provisions ONLY the AWS data plane that the locally-run StrataBI
# app talks to: the async-Athena + status-writer Lambdas, the awswrangler layer,
# a Glue catalog database, Athena workgroups, the runtime DynamoDB tables, and
# the system S3 bucket (dashboards, modules, themes, results).
#
# It intentionally does NOT deploy any application hosting (no ECS, ALB, target
# groups, listeners, VPC subnets, NAT, EIP, or ECR). In this edition you run the
# Primary Runtime locally (`python -m stratabi.app`) with your own AWS
# credentials. Managed/hosted deployment is an Enterprise pattern (see the
# ShaleIO Guild Community License, Section 5.6).
#
# Local permissions: instead of an ECS task role, this stack emits a managed
# IAM policy AND a matching assumable IAM role (see iam_local_runtime below) so
# your local credentials get exactly the runtime permissions they need.
# ============================================================================

data "archive_file" "status_writer_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/status_writer"
  output_path = "${path.module}/build/status_writer.zip"
}

data "archive_file" "athena_async_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/athena_async"
  output_path = "${path.module}/build/athena_async.zip"
}

data "aws_caller_identity" "current" {}

provider "aws" {
  region = var.region
}

locals {
  stratabi_bucket_name    = aws_s3_bucket.stratabi_system.bucket
  stratabi_bucket_arn     = "arn:aws:s3:::${aws_s3_bucket.stratabi_system.bucket}"
  stratabi_bucket_objects = "arn:aws:s3:::${aws_s3_bucket.stratabi_system.bucket}/*"

  stratabi_module_prefix        = "analyst/modules"
  stratabi_tmp_prefix           = "tmp"
  stratabi_result_prefix        = "runtime/results"
  stratabi_source_value_prefix  = "analyst/source_values"
  stratabi_runtime_table_prefix = "runtime/tables"

  wg_numbers  = toset([for i in range(var.athena_workgroup_count) : format("%02d", i + 1)])
  theme_files = fileset("${path.module}/../stratabi/themes", "*.css")

  # Principals allowed to assume the local-runtime role. Empty = the account
  # root (any IAM principal in this account that also has sts:AssumeRole).
  local_runtime_trust_principals = length(var.local_runtime_assume_principals) > 0 ? var.local_runtime_assume_principals : ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
}

# ----------------------------------------------------------------------------
# Lambdas: async Athena runner + status writer
# ----------------------------------------------------------------------------
resource "aws_lambda_function" "stratabi_status_writer" {
  function_name = "${var.name_prefix}-status-writer"
  role          = aws_iam_role.stratabi_lambda_role.arn
  handler       = "status_writer.lambda_handler"
  runtime       = "python3.12"

  filename         = data.archive_file.status_writer_zip.output_path
  source_code_hash = data.archive_file.status_writer_zip.output_base64sha256

  timeout     = 10
  memory_size = 128

  environment {
    variables = {
      STRATABI_TILE_STATUS_TABLE  = aws_dynamodb_table.stratabi_tile_status.name
      STRATABI_STATUS_TTL_SECONDS = "86400"
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic,
    aws_iam_role_policy.lambda_stratabi_permissions
  ]
}

resource "aws_lambda_function" "stratabi_athena_async" {
  function_name = "${var.name_prefix}-athena-async"
  role          = aws_iam_role.stratabi_lambda_role.arn
  handler       = "athena_async.lambda_handler"
  runtime       = "python3.13"

  architectures = ["arm64"]

  layers = [
    aws_lambda_layer_version.awswrangler_py313_arm64.arn
  ]

  filename         = data.archive_file.athena_async_zip.output_path
  source_code_hash = data.archive_file.athena_async_zip.output_base64sha256

  timeout     = 900
  memory_size = 1024

  environment {
    variables = {
      STRATABI_TILE_STATUS_TABLE    = aws_dynamodb_table.stratabi_tile_status.name
      STRATABI_WORKGROUPS           = join(",", [for n in local.wg_numbers : "${var.name_prefix}-wg-${n}"])
      STRATABI_STATUS_TTL_SECONDS   = "86400"
      STRATABI_RESULT_PREFIX        = local.stratabi_result_prefix
      STRATABI_ATHENA_OUTPUT        = "s3://${local.stratabi_bucket_name}/athena/"
      STRATABI_CATALOG_DATABASE     = aws_glue_catalog_database.stratabi.name
      STRATABI_RUNTIME_TABLE_PREFIX = local.stratabi_runtime_table_prefix
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic,
    aws_iam_role_policy.lambda_stratabi_permissions,
    aws_lambda_layer_version.awswrangler_py313_arm64
  ]
}

resource "aws_lambda_layer_version" "awswrangler_py313_arm64" {
  layer_name = "${var.name_prefix}-awswrangler-py313-arm64"

  s3_bucket = aws_s3_object.awswrangler_layer_zip.bucket
  s3_key    = aws_s3_object.awswrangler_layer_zip.key

  source_code_hash = filebase64sha256("${path.module}/lambda/awswrangler-layer-3.16.1-py3.13-arm64.zip")

  compatible_runtimes      = ["python3.13"]
  compatible_architectures = ["arm64"]

  description = "AWS SDK for pandas / awswrangler layer for StrataBI async Athena parquet runtime."

  depends_on = [
    aws_s3_object.awswrangler_layer_zip
  ]
}

# ----------------------------------------------------------------------------
# Glue catalog + Athena workgroups
# ----------------------------------------------------------------------------
resource "aws_glue_catalog_database" "stratabi" {
  name        = "stratabi"
  description = "StrataBI-managed runtime catalog database for temporary and managed query objects."
}

resource "aws_athena_workgroup" "stratabi" {
  count = var.enable_athena_workgroup ? 1 : 0

  name = "stratabi"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location = "s3://${local.stratabi_bucket_name}/athena/"
    }
  }
}

resource "aws_athena_workgroup" "sharded" {
  for_each = local.wg_numbers

  name = "${var.name_prefix}-wg-${each.key}"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location = "s3://${local.stratabi_bucket_name}/athena/${each.key}/"
    }
  }
}

# ----------------------------------------------------------------------------
# DynamoDB runtime tables
# ----------------------------------------------------------------------------
resource "aws_dynamodb_table" "stratabi_tile_status" {
  name         = "${var.name_prefix}_tile_status"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "runtime_tile_key"
  range_key    = "run_id"

  attribute {
    name = "runtime_tile_key"
    type = "S"
  }

  attribute {
    name = "run_id"
    type = "S"
  }

  attribute {
    name = "updated_at"
    type = "S"
  }

  attribute {
    name = "dashboard_tile_key"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  global_secondary_index {
    name            = "runtime-tile-updated-index"
    hash_key        = "runtime_tile_key"
    range_key       = "updated_at"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "dashboard-tile-updated-index"
    hash_key        = "dashboard_tile_key"
    range_key       = "updated_at"
    projection_type = "ALL"
  }

  tags = {
    Project = "stratabi"
  }
}

resource "aws_dynamodb_table" "stratabi_dashboard_git_registry" {
  name         = "${var.name_prefix}-dashboard-git-registry"
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "pk"
  range_key = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Project = "stratabi"
  }
}

resource "aws_dynamodb_table" "stratabi_source_registry" {
  name         = "${var.name_prefix}_source_registry"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "source_id"

  attribute {
    name = "source_id"
    type = "S"
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Project = "stratabi"
  }
}

resource "aws_dynamodb_table" "stratabi_module_registry" {
  name         = "${var.name_prefix}_module_registry"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "module_id"

  attribute {
    name = "module_id"
    type = "S"
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Project = "stratabi"
  }
}

# ----------------------------------------------------------------------------
# System S3 bucket + lifecycle + bootstrap objects/prefixes
# ----------------------------------------------------------------------------
resource "aws_s3_bucket" "stratabi_system" {
  bucket = "${var.name_prefix}-system-${data.aws_caller_identity.current.account_id}"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "stratabi_system_lifecycle" {
  bucket = aws_s3_bucket.stratabi_system.id

  rule {
    id     = "expire-tmp-after-1-day"
    status = "Enabled"

    filter {
      prefix = "${local.stratabi_tmp_prefix}/"
    }

    expiration {
      days = 1
    }
  }

  rule {
    id     = "expire-runtime-results-after-2-days"
    status = "Enabled"

    filter {
      prefix = "${local.stratabi_result_prefix}/"
    }

    expiration {
      days = 2
    }
  }
}

resource "aws_s3_object" "awswrangler_layer_zip" {
  bucket = aws_s3_bucket.stratabi_system.bucket
  key    = "lambda-layers/awswrangler/awswrangler-layer-3.16.1-py3.13-arm64.zip"
  source = "${path.module}/lambda/awswrangler-layer-3.16.1-py3.13-arm64.zip"
  etag   = filemd5("${path.module}/lambda/awswrangler-layer-3.16.1-py3.13-arm64.zip")
}

resource "aws_s3_object" "runtime_tables_prefix" {
  bucket  = aws_s3_bucket.stratabi_system.bucket
  key     = "${local.stratabi_runtime_table_prefix}/"
  content = ""
}

resource "aws_s3_object" "theme_files" {
  for_each = local.theme_files

  bucket       = aws_s3_bucket.stratabi_system.bucket
  key          = "analyst/themes/${each.value}"
  source       = "${path.module}/../stratabi/themes/${each.value}"
  content_type = "text/css"
  etag         = filemd5("${path.module}/../stratabi/themes/${each.value}")
}

resource "aws_s3_object" "themes_registry" {
  bucket       = aws_s3_bucket.stratabi_system.bucket
  key          = "analyst/themes/themes.json"
  source       = "${path.module}/../stratabi/themes/themes.json"
  content_type = "application/json"
  etag         = filemd5("${path.module}/../stratabi/themes/themes.json")
}

resource "aws_s3_object" "default_dashboard" {
  bucket       = aws_s3_bucket.stratabi_system.bucket
  key          = "analyst/dashboards/default.json"
  source       = "${path.module}/bootstrap/default.json"
  content_type = "application/json"
  etag         = filemd5("${path.module}/bootstrap/default.json")
}

resource "aws_s3_object" "module_prefix" {
  bucket  = aws_s3_bucket.stratabi_system.bucket
  key     = "${local.stratabi_module_prefix}/"
  content = ""
}

resource "aws_s3_object" "runtime_results_prefix" {
  bucket  = aws_s3_bucket.stratabi_system.bucket
  key     = "${local.stratabi_result_prefix}/"
  content = ""
}

resource "aws_s3_object" "source_value_prefix" {
  bucket  = aws_s3_bucket.stratabi_system.bucket
  key     = "${local.stratabi_source_value_prefix}/"
  content = ""
}

resource "aws_s3_object" "tmp_prefix" {
  bucket  = aws_s3_bucket.stratabi_system.bucket
  key     = "${local.stratabi_tmp_prefix}/"
  content = ""
}

# ----------------------------------------------------------------------------
# Lambda execution role + policies
# ----------------------------------------------------------------------------
resource "aws_iam_role" "stratabi_lambda_role" {
  name = "${var.name_prefix}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "lambda.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.stratabi_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_invoke_status_writer" {
  name = "${var.name_prefix}-lambda-invoke-status-writer-policy"
  role = aws_iam_role.stratabi_lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect   = "Allow",
        Action   = ["lambda:InvokeFunction"],
        Resource = aws_lambda_function.stratabi_status_writer.arn
      }
    ]
  })
}

resource "aws_iam_role_policy" "lambda_stratabi_permissions" {
  name = "${var.name_prefix}-lambda-policy"
  role = aws_iam_role.stratabi_lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:GetItem"
        ],
        Resource = [
          aws_dynamodb_table.stratabi_tile_status.arn,
          "${aws_dynamodb_table.stratabi_tile_status.arn}/index/*",
          aws_dynamodb_table.stratabi_module_registry.arn,
          "${aws_dynamodb_table.stratabi_module_registry.arn}/index/*",
          aws_dynamodb_table.stratabi_source_registry.arn,
          "${aws_dynamodb_table.stratabi_source_registry.arn}/index/*"
        ]
      },
      {
        Effect = "Allow",
        Action = [
          "s3:ListBucket",
          "s3:GetBucketLocation",
          "s3:ListBucketMultipartUploads"
        ],
        Resource = [local.stratabi_bucket_arn]
      },
      {
        Effect = "Allow",
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject",
          "s3:AbortMultipartUpload",
          "s3:ListMultipartUploadParts"
        ],
        Resource = [local.stratabi_bucket_objects]
      },
      {
        Effect = "Allow",
        Action = [
          "athena:StartQueryExecution",
          "athena:GetQueryExecution",
          "athena:GetQueryResults",
          "athena:GetWorkGroup",
          "athena:StopQueryExecution"
        ],
        Resource = "*"
      },
      {
        Effect = "Allow",
        Action = [
          "glue:GetDatabase",
          "glue:GetDatabases",
          "glue:GetTable",
          "glue:GetTables",
          "glue:GetPartition",
          "glue:GetPartitions",
          "glue:CreateDatabase",
          "glue:CreateTable",
          "glue:UpdateTable",
          "glue:DeleteTable",
          "glue:BatchCreatePartition",
          "glue:BatchDeletePartition",
          "glue:BatchGetPartition"
        ],
        Resource = "*"
      }
    ]
  })
}

# ----------------------------------------------------------------------------
# Local runtime IAM (replaces the ECS task role)
#
# The locally-run StrataBI app needs the runtime permissions the ECS task role
# used to provide. We emit BOTH:
#   * a managed policy you can attach directly to your own IAM user/role, and
#   * a dedicated assumable role (same permissions) for least-privilege / CI use.
# Bedrock is intentionally NOT included.
# ----------------------------------------------------------------------------
data "aws_iam_policy_document" "local_runtime" {
  statement {
    sid     = "S3Bucket"
    effect  = "Allow"
    actions = [
      "s3:ListBucket",
      "s3:GetBucketLocation",
      "s3:ListBucketMultipartUploads"
    ]
    resources = [local.stratabi_bucket_arn]
  }

  statement {
    sid     = "S3Objects"
    effect  = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts"
    ]
    resources = [local.stratabi_bucket_objects]
  }

  statement {
    sid     = "InvokeRuntimeAndModuleLambdas"
    effect  = "Allow"
    actions = ["lambda:InvokeFunction"]
    # Covers the async runner, the status writer, and customer-owned module
    # Lambdas (arbitrary names resolved from the module registry). Narrow to
    # specific ARNs or a name prefix if you prefer tighter scope.
    resources = ["*"]
  }

  statement {
    sid     = "DynamoDB"
    effect  = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:Query",
      "dynamodb:Scan",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem"
    ]
    resources = [
      aws_dynamodb_table.stratabi_tile_status.arn,
      "${aws_dynamodb_table.stratabi_tile_status.arn}/index/*",
      aws_dynamodb_table.stratabi_module_registry.arn,
      "${aws_dynamodb_table.stratabi_module_registry.arn}/index/*",
      aws_dynamodb_table.stratabi_source_registry.arn,
      "${aws_dynamodb_table.stratabi_source_registry.arn}/index/*",
      aws_dynamodb_table.stratabi_dashboard_git_registry.arn,
      "${aws_dynamodb_table.stratabi_dashboard_git_registry.arn}/index/*"
    ]
  }

  statement {
    sid     = "Glue"
    effect  = "Allow"
    actions = [
      "glue:GetDatabase",
      "glue:GetDatabases",
      "glue:GetTable",
      "glue:GetTables",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:DeleteTable",
      "glue:BatchCreatePartition",
      "glue:BatchDeletePartition",
      "glue:BatchGetPartition"
    ]
    resources = ["*"]
  }

  statement {
    sid     = "Athena"
    effect  = "Allow"
    actions = [
      "athena:StartQueryExecution",
      "athena:GetQueryExecution",
      "athena:GetQueryResults",
      "athena:GetWorkGroup",
      "athena:StopQueryExecution"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "local_runtime" {
  name        = "${var.name_prefix}-local-runtime"
  description = "Runtime permissions for a locally-run StrataBI Developer Edition instance. Attach to your IAM user, or assume the companion role."
  policy      = data.aws_iam_policy_document.local_runtime.json
}

data "aws_iam_policy_document" "local_runtime_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "AWS"
      identifiers = local.local_runtime_trust_principals
    }
  }
}

resource "aws_iam_role" "local_runtime" {
  name               = "${var.name_prefix}-local-runtime"
  description        = "Assumable role granting StrataBI Developer Edition runtime permissions for local use."
  assume_role_policy = data.aws_iam_policy_document.local_runtime_trust.json
}

resource "aws_iam_role_policy_attachment" "local_runtime" {
  role       = aws_iam_role.local_runtime.name
  policy_arn = aws_iam_policy.local_runtime.arn
}
