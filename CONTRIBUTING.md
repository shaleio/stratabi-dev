# Contributing to StrataBI Developer Edition

Thanks for your interest. Please read this together with [`LICENSE.md`](./LICENSE.md)
(the Shaleio Guild Community License, "SGCL"). This project is **source-available**,
not OSI open source.

> **Note:** the contribution terms below are governed by the SGCL. Where anything here
> differs from the SGCL, **the SGCL controls.** Shaleio's counsel is reviewing the
> inbound-contribution language; see `LEGAL_REVIEW.md`.

## Licensing of contributions

- By submitting a contribution (pull request, patch, or otherwise), you agree it is
  provided under the SGCL's contribution provisions and that you have the right to
  submit it.
- Do not submit code you do not have the right to license under the SGCL, and do not
  paste code from incompatibly-licensed sources.

## Before you open a PR

1. **Discuss large changes first** — open an issue describing the problem.
2. **Keep the edition's boundaries.** This is the data-plane / local runtime edition:
   no Enterprise-only features (RBAC, admin console, managed/hosted deployment, ECS/ALB
   topology). Those belong to the Enterprise edition and are out of scope here.
3. **Style & checks:**
   ```bash
   pip install -e '.[dev]'
   python -m pytest
   python -m compileall stratabi
   ```
4. **No secrets.** Never commit credentials, `.env`, `terraform.tfvars`, or Terraform
   state (all are git-ignored).

## What we welcome

Bug fixes, docs improvements, block/rendering fixes, module-authoring ergonomics,
and portability fixes. Feature proposals are welcome as issues first.

## What we can't accept

Changes that reintroduce Enterprise-only capabilities, that repackage StrataBI as a
hosted/managed service, or that conflict with the SGCL.

## Support

There is no support or SLA for the Developer Edition. For security issues, see
[`SECURITY.md`](./SECURITY.md).
