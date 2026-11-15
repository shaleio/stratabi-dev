# StrataBI Developer Edition — data plane (Terraform / OpenTofu)

This module provisions the **data plane** a locally-run StrataBI Developer Edition talks to, in
**one AWS account**. There is no hosted app here: no ALB, ECS, VPC, ECR or Cognito — the app runs
on your machine (`stratabi`) with your AWS credentials.

What it creates:

- **S3 system bucket** (`<name_prefix>-system-<account>`) seeded with the themes and a default
  dashboard, plus the runtime prefixes (results, modules, source values, tmp).
- **Athena + Glue:** a Glue catalog database and sharded Athena workgroups (`<name_prefix>-wg-NN`).
- **Lambdas:** `<name_prefix>-athena-async` (async Athena runner) and `<name_prefix>-status-writer`
  (module/tile run status), with an awswrangler layer.
- **DynamoDB:** tile status, module registry, source registry, and the dashboard **git registry**
  (dashboards-as-code: `stratactl dashboards … --git-registered`).
- **IAM:** the Lambda role, and a `<name_prefix>-local-runtime` policy + assumable role with exactly
  the permissions the local app needs.

## Prerequisites

- An AWS account and credentials allowed to create the resources above.
- OpenTofu or Terraform >= 1.6.

The simplest path is StrataCTL, which runs this for you:

```bash
stratactl dev install            # deploy the data plane
stratactl dev configure-local    # write a non-secret .env from the outputs
stratabi                         # run the app on http://127.0.0.1:8050
```

## Running it yourself

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars   # then edit
tofu init
tofu validate
tofu plan          # review carefully (see "Safety notes")
tofu apply
tofu output -raw env_file_preview > ../.env    # the STRATABI_* settings for the local app
```

Attach the `local_runtime_policy_arn` output to your IAM user, or assume `local_runtime_role_arn`
(set `local_runtime_assume_principals` to restrict who may).

## Multiple installs in one account

Every named resource is prefixed by `var.name_prefix` (default `stratabi`). For a second install in
the same account, set a distinct prefix before the first apply:

```hcl
name_prefix = "acme"
```

The Glue catalog database is intentionally **not** prefixed (the catalog is shared).

## Safety notes

- The S3 system bucket and the DynamoDB tables carry `prevent_destroy = true`. This is deliberate
  (your data) but means `destroy`, and any change that would *replace* them (such as changing
  `name_prefix` on an existing install), is blocked. Choose `name_prefix` before the first apply.
- Always run `validate` and review `plan` before `apply`.

## Smoke test

After `apply`, verify the install:

```bash
./smoke_test.sh stratabi us-east-1     # <name_prefix> <region>
```

It checks the Lambdas, DynamoDB tables, Athena workgroups and the S3 bucket exist.
