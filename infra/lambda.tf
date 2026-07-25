# lambda.tf
#
# The previous `aws_lambda_function.custom_tile` resource was removed.
#
# Why: it auto-deployed lambda_templates/simple_python as a single fixed Lambda
# ("stratabi_custom_tile") wired with the stale async contract and the wrong env
# var names (STRATABI_STATUS_TABLE / STRATABI_BUCKET). It was orphaned — nothing
# in the app or in main.tf referenced it — and it is superseded by the module
# registry + async-Athena design.
#
# Module Lambdas are customer-owned extensions. They are NOT provisioned by core
# infra. Build them from lambda_templates/{simple_python,python_w_deps}, deploy
# them with their own Terraform/CLI, and register them in the module registry
# table (aws_dynamodb_table.stratabi_module_registry) so exec.type == "lambda"
# tiles can resolve module_id + lambda_index to an ARN.
#
# The core async Athena runner and status writer Lambdas remain defined in
# main.tf.
