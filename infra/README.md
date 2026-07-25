# StrataBI — Install (Terraform)

This module provisions a complete, customer-owned StrataBI runtime in **one AWS
account**: ALB + ECS Fargate (the Dash app), the async Athena runner and status
writer Lambdas, DynamoDB tables (tile status, module/source registries,
favorites/pinned/recents), a Glue catalog database, sharded Athena workgroups,
and an S3 system bucket seeded with themes and a default dashboard.

## Prerequisites

- An AWS account and credentials with permission to create the resources above.
- Terraform >= 1.6.
- An existing VPC with public subnets (for the ALB) and subnets for ECS tasks.
- A built StrataBI container image pushed to ECR (`stratabi_image`). The ECR
  repository `stratabi` is created by this module and can be shared across
  installs in the same account.
- (Optional) An ACM certificate in the same region if you enable HTTPS.

## Quick start

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars   # then edit
terraform init
terraform validate
terraform plan        # review carefully (see "Safety notes")
terraform apply
```

After apply, the app is reachable at the ALB DNS name:

```bash
terraform output alb_dns_name
```

## Multiple installs in one account

Every named resource is prefixed by `var.name_prefix` (default `stratabi`). The
default reproduces the original names exactly, so existing installs see **no
change**. For a second install in the same account, set a distinct prefix:

```hcl
name_prefix = "acme"
```

Note: the ECR repository and the Glue catalog database are intentionally **not**
prefixed (the image is the same product; the catalog is shared). If you need
fully isolated catalogs per install in one account, that is a follow-up.

## HTTPS

HTTPS is off by default (the ALB serves plain HTTP on :80). To enable TLS:

```hcl
enable_https        = true
acm_certificate_arn = "arn:aws:acm:us-east-1:<acct>:certificate/<id>"
```

This adds a :443 listener and a :443 ALB ingress rule. The :80 listener is left
in place (still forwarding) so nothing breaks. For production you typically want
:80 to **redirect** to :443 — change the `aws_lb_listener.http` default action
to a `redirect` block once HTTPS is verified.

## Safety notes

- The S3 system bucket and the DynamoDB tables carry `prevent_destroy = true`.
  This is deliberate (customer data) but means `terraform destroy` and any change
  that would *replace* them (such as renaming via `name_prefix` on an existing
  install) will be blocked. Choose `name_prefix` before the first apply.
- `terraform` is not bundled here; always run `terraform validate` and review
  `terraform plan` before `apply`. With the default `name_prefix`, the plan
  should show **no changes** to names.
- `allowed_ip_cidrs` defaults to open (`0.0.0.0/0`). Restrict it.

## Smoke test

After `apply`, verify the install:

```bash
./smoke_test.sh stratabi us-east-1     # <name_prefix> <region>
```

It checks the ALB, ECS service, Lambdas, DynamoDB tables, and S3 bucket exist
and are healthy.
