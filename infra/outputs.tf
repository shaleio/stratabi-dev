# ============================================================================
# Outputs — copy these into your local .env (see README "Wiring .env").
# Convenience: `tofu output -raw env_file_preview >> ../.env`
# ============================================================================

output "system_bucket" {
  description = "StrataBI system S3 bucket (dashboards, modules, themes, results)."
  value       = aws_s3_bucket.stratabi_system.bucket
}

output "athena_output_uri" {
  description = "Athena query result location."
  value       = "s3://${aws_s3_bucket.stratabi_system.bucket}/athena/"
}

output "athena_workgroups" {
  description = "Sharded Athena workgroup names."
  value       = [for wg in aws_athena_workgroup.sharded : wg.name]
}

output "catalog_database" {
  description = "Glue/Athena catalog database name."
  value       = aws_glue_catalog_database.stratabi.name
}

output "tile_status_table" {
  value = aws_dynamodb_table.stratabi_tile_status.name
}

output "module_registry_table" {
  value = aws_dynamodb_table.stratabi_module_registry.name
}

output "source_registry_table" {
  value = aws_dynamodb_table.stratabi_source_registry.name
}

output "athena_async_lambda_arn" {
  value = aws_lambda_function.stratabi_athena_async.arn
}

output "status_writer_lambda_arn" {
  value = aws_lambda_function.stratabi_status_writer.arn
}

output "module_prefix" {
  value = local.stratabi_module_prefix
}

output "result_prefix" {
  value = local.stratabi_result_prefix
}

output "local_runtime_policy_arn" {
  description = "Attach this managed policy to your own IAM user/role for local runs."
  value       = aws_iam_policy.local_runtime.arn
}

output "local_runtime_role_arn" {
  description = "Assume this role for least-privilege/short-lived local credentials."
  value       = aws_iam_role.local_runtime.arn
}

# A ready-to-paste block of STRATABI_* values for your local .env.
output "env_file_preview" {
  description = "Render with: tofu output -raw env_file_preview"
  value       = <<-EOT
    STRATABI_MODE=aws
    STRATABI_BUCKET=${aws_s3_bucket.stratabi_system.bucket}
    STRATABI_SYSTEM_BUCKET=${aws_s3_bucket.stratabi_system.bucket}
    STRATABI_DASHBOARD_PREFIX=analyst/dashboards
    STRATABI_MODULE_PREFIX=${local.stratabi_module_prefix}
    STRATABI_THEME_PREFIX=analyst/themes
    STRATABI_RESULT_PREFIX=${local.stratabi_result_prefix}
    STRATABI_ATHENA_OUTPUT=s3://${aws_s3_bucket.stratabi_system.bucket}/athena/
    STRATABI_CATALOG_DATABASE=${aws_glue_catalog_database.stratabi.name}
    STRATABI_WORKGROUPS=${join(",", [for wg in aws_athena_workgroup.sharded : wg.name])}
    STRATABI_ATHENA_ASYNC_LAMBDA_ARN=${aws_lambda_function.stratabi_athena_async.arn}
    STRATABI_STATUS_WRITER_LAMBDA_ARN=${aws_lambda_function.stratabi_status_writer.arn}
    STRATABI_TILE_STATUS_TABLE=${aws_dynamodb_table.stratabi_tile_status.name}
    STRATABI_MODULE_REGISTRY_TABLE=${aws_dynamodb_table.stratabi_module_registry.name}
    STRATABI_SOURCE_REGISTRY_TABLE=${aws_dynamodb_table.stratabi_source_registry.name}
    STRATABI_DASHBOARD_GIT_REGISTRY=${aws_dynamodb_table.stratabi_dashboard_git_registry.name}
    STRATABI_RUNTIME_TABLE_PREFIX=${local.stratabi_runtime_table_prefix}
    STRATABI_STATUS_TTL_SECONDS=86400
  EOT
}

output "git_registry_table" {
  description = "Dashboard git registry table (StrataCLI dashboards commands)."
  value       = aws_dynamodb_table.stratabi_dashboard_git_registry.name
}
