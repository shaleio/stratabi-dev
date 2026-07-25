variable "region" {
  type        = string
  description = "AWS region for the StrataBI data plane."
  default     = "us-east-1"
}

variable "name_prefix" {
  type        = string
  description = "Prefix for all named AWS resources, enabling multiple StrataBI installs in one account. Keep short: IAM roles/Lambda names must be <= 64 chars."
  default     = "stratabi"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,20}$", var.name_prefix))
    error_message = "name_prefix must be lowercase alphanumeric/hyphen, start with a letter, and be <= 21 chars."
  }
}

variable "enable_athena_workgroup" {
  type        = bool
  description = "Also create a single legacy 'stratabi' Athena workgroup in addition to the sharded workgroups."
  default     = false
}

variable "athena_workgroup_count" {
  type        = number
  description = "Number of sharded Athena workgroups to create for auto-sharded query execution (named <name_prefix>-wg-NN)."
  default     = 5
}

variable "local_runtime_assume_principals" {
  type        = list(string)
  description = "IAM principal ARNs allowed to assume the local-runtime role (e.g. [\"arn:aws:iam::123456789012:user/alex\"]). Leave empty to trust the account root, which lets any IAM principal in the account that also has sts:AssumeRole permission assume it."
  default     = []
}
