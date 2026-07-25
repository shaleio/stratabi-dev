# Security Policy — StrataBI Developer Edition

## Reporting a vulnerability

Email **info@shaleio.com** with details and reproduction steps. Please do **not**
open a public issue for security reports. We aim to acknowledge within a few business
days. There is no paid bug-bounty program.

## Scope & threat model

StrataBI Dev is a **local developer tool** that runs on your machine against **your own
AWS account** using your credentials.

- It binds to **loopback (`127.0.0.1`) by default** and has **no built-in
  authentication**. Do not bind it to a public interface (`--host 0.0.0.0`) or expose
  it to untrusted networks.
- It uses the standard AWS credential provider chain. **Do not commit credentials.**
  `.env`, `terraform.tfvars`, and Terraform state are git-ignored — keep them local.
- All data stays in **your** AWS account; StrataBI Dev does not send your data to
  Shaleio.

## What is and isn't covered

In scope: issues in this repository's code (the Dash runtime, the data-plane
Terraform). Out of scope: your AWS account configuration, third-party dependencies'
own advisories (report those upstream), and Enterprise/StrataHQ components (separate,
private).

## Supported versions

The Developer Edition is provided **without an SLA**. Fixes land on `main`; there is no
back-port guarantee for older tags.
