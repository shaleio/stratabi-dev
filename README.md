# StrataBI — Developer Edition

A client-owned business-intelligence runtime for AWS. **This is the local
developer edition:** you run the StrataBI app on your own machine (a plain Python
process on `localhost:8050` — no Docker, no Fargate) wired to a real AWS data plane
(Athena · Lambda · S3 · DynamoDB) in **your own AWS account**. It's built for
module development, dashboard authoring, and ad-hoc analytics.

```
your laptop / AWS WorkSpaces                 your AWS account
┌─────────────────────────┐                 ┌───────────────────────────────┐
│  stratabi-dev            │  boto3 (creds)  │  S3 · Athena · Glue           │
│  http://127.0.0.1:8050   │ ───────────────▶│  Lambda (async + status)      │
│  (Dash / Plotly)         │                 │  DynamoDB (status + registries)│
└─────────────────────────┘                 └───────────────────────────────┘
```

## License — please read first

StrataBI Developer Edition is **source-available**, governed by the **Shaleio Guild
Community License (SGCL), Version 1.0** — see [`LICENSE.md`](./LICENSE.md) (canonical
copy: `LICENSE.docx`).

- It is **not** Apache, MIT, BSD, GPL, or any other OSI-approved open-source license,
  and is **not** "open source."
- Use is subject to the SGCL. In particular, the SGCL permits self-managed developer
  and evaluation use, and **prohibits** resale, white-labeling, managed/hosted service
  offerings, competing commercial offerings, and use of Enterprise-only deployment
  patterns (including **Managed Application Hosting**) without a separate commercial
  license.
- The **Primary Runtime** deployment boundaries and **Enterprise-Feature** restrictions
  in the SGCL apply. This README is a convenience summary and **does not replace** the
  license text.

Bundled third-party components (the Monaco editor and Plotly.js, both MIT) are
acknowledged in [`THIRD_PARTY_NOTICES.md`](./THIRD_PARTY_NOTICES.md).

**Costs & support.** StrataBI Dev runs against **your** AWS account — **you are
responsible for all AWS and third-party costs** it incurs. The Developer Edition is
provided **without support and without any SLA**.

## Two ways to install

### A. pipx (local runtime)

```bash
pipx install stratabi-dev
stratabi-dev --check      # preflight: deps, AWS creds/region, STRATABI_* settings
stratabi-dev              # serves http://127.0.0.1:8050
```

The runtime needs a data plane in your account and a few `STRATABI_*` settings. Get
them either with the CLI (below) or manually (Path B).

#### With StrataCLI (optional — provisions the data plane for you)

```bash
pipx install stratacli
stratacli bootstrap --profile <aws-profile> --region <aws-region>   # one-time: StrataCI
stratacli dev install                                               # deploy the Dev data plane (HQ-free)
stratacli dev configure-local                                       # write non-secret .env (no AWS keys)
stratabi-dev                                                        # run the app
```

Developer Edition installation via StrataCLI **never contacts StrataHQ** and requires
no license contract — the artifact comes from a public GitHub release, your own S3, or
the conventional bucket key.

### B. Manual — no StrataCLI required

You can inspect and run everything by hand:

```bash
# 1) code + venv
git clone https://github.com/shaleio/stratabi-dev && cd stratabi-dev
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .                                        # or: pip install stratabi-dev

# 2) data plane (OpenTofu 1.6+ / Terraform 1.6+) — creates S3/Athena/Glue/DynamoDB + 2 Lambdas
cd infra
cp terraform.tfvars.example terraform.tfvars           # edit region / name_prefix
tofu init && tofu apply
tofu output -raw env_file_preview >> ../.env           # ready-made STRATABI_* block
cd ..

# 3) credentials — set AWS_PROFILE (or keys) + AWS_REGION in .env, attach the emitted
#    data-plane policy to your IAM identity (see infra outputs), then:
stratabi-dev
```

The app loads a local `.env` at startup. See [`.env.example`](./.env.example) for the
full annotated list of settings.

## CLI

```
stratabi-dev [--host 127.0.0.1] [--port 8050] [--debug] [--check] [--version]
```

- Binds to **loopback by default** — this is a local developer tool with no built-in
  auth. Use `--host 0.0.0.0` only in a trusted environment (e.g. a WorkSpaces desktop);
  do not expose it publicly.
- `--check` validates dependencies, AWS credentials/region, and required `STRATABI_*`
  settings, then exits — no network calls.
- Health endpoint: `GET /healthz` → `{"status":"ok"}`.

## Requirements

- **Python 3.11+**
- An **AWS account** + credentials (standard boto3 provider chain)
- **OpenTofu 1.6+** or **Terraform 1.6+** to stand up the data plane

Works the same on a local machine, an **AWS WorkSpaces** desktop, or **CloudShell** —
all permitted developer environments under the SGCL.

## ForgeWorks demo

A first-party synthetic demo — **ForgeWorks Distribution** (fictional company, all
data synthetic) — that runs two ways from the same canonical dataset.

**Quick Demo (validates the local StrataBI experience).** No AWS, no credentials, no
network — deterministic data baked into static blocks.

```bash
stratabi-dev demo quick            # generate + open the Quick Demo
stratabi-dev demo generate         # generate assets only (no launch)
stratabi-dev demo status
stratabi-dev demo remove-local     # remove local demo assets
```

Badge in the UI: *ForgeWorks Quick Demo — Embedded synthetic data*.

**AWS Demo (validates the customer-owned Athena data plane).** Uploads the same data
to **your** StrataBI Dev data plane and queries it through Athena. Explicit and
namespaced; also available via `stratacli dev demo`.

```bash
stratabi-dev demo aws install      # confirm before creating anything (--yes to skip)
stratabi-dev demo aws status
stratabi-dev demo aws remove
```

**What it creates:** CSVs under `s3://<your-bucket>/demo/forgeworks/v1/`, an isolated
Glue database `stratabi_dev_demo` with explicit external tables (no crawler), and the
`forgeworks_athena_demo` dashboard. **Expected AWS services:** S3, Glue, Athena.

**Cost notice:** uploading synthetic CSVs and creating Glue tables in your account, and
running Athena queries, may incur small AWS charges. **No data is transmitted to
Shaleio.**

**Remove it:** `stratabi-dev demo aws remove` deletes **only** the ForgeWorks demo
namespace (its S3 prefix, its Glue tables/database, its dashboard) — never the StrataBI
Dev data plane or any non-demo data.

**Synthetic-data statement:** ForgeWorks Distribution is fictional. All data is
synthetic. Any resemblance to real entities or records is coincidental.

> Quick Demo validates the local StrataBI experience. AWS Demo validates the
> customer-owned Athena data plane.

## What's in the box (and what isn't)

Intentionally slimmer than the hosted Enterprise edition: no admin console, no AI
splash, no RBAC, no favorites/pinned overlays. The `infra/` here provisions **only the
data plane** — no ECS/ALB/VPC/ECR. Managed/hosted deployment is an Enterprise pattern
(SGCL §5.6). Uninstall by destroying the data plane (`tofu destroy` in `infra/`, or
`stratacli dev uninstall`); this removes the system resources you created.

## Building modules

Modules are customer-owned compute extensions and are **not** provisioned by this core
infra. Build one from the templates, deploy its Lambda, upload its `module.json` under
the `analyst/modules/` prefix in the system bucket, and register it in the
`*_module_registry` DynamoDB table. Full contract + examples: https://shaleio.com/docs.

## Building the data-plane bundle (maintainers)

```bash
python build_module_bundle.py --out dist
# → dist/stratabi_dev-<version>-module.zip + .sha256 + release manifest (deterministic)
```

## Development

```bash
pip install -e '.[dev]'         # pytest/build/twine
python -m pytest                # tests
python -m build                 # wheel + sdist
```

## Versioning

Shaleio versions are **`Major.Sprint.Patch`**, not SemVer. The middle number is the
Shaleio **sprint** the release was cut in — a shared 2-week clock across the whole
ecosystem (Sprint 0 begins 2026-07-27), so it is the same for every Shaleio project
released in that sprint. `PATCH` increments within a sprint; `MAJOR` is a deliberate
milestone. The versions are still valid `MAJOR.MINOR.PATCH` triples, so SemVer-based
tooling parses them fine — the middle number just carries ecosystem meaning.

## Contributing

See [`CONTRIBUTING.md`](./CONTRIBUTING.md). Contributions are accepted under the SGCL's
contribution terms.
