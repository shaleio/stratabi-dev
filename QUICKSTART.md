<!--
SCAFFOLD FOR REVIEW. This is designed to become the top of the stratabi PyPI README
and the website Quickstart. Inline "> **Review:**" callouts flag decisions for Alex.
Philosophy: hand-hold every layer; skippable sections; link out but always give the
actual command/installer too.
-->

# StrataBI Developer Edition — Quickstart

**Goal: from nothing to live dashboards in ~15 minutes, running entirely in _your_ AWS account.** Nothing you build leaves your account; there's no SaaS to sign into.

Each step below is self-contained. **If you already have a tool, skip its section.** The "check" command at the top of each section tells you whether you can skip it.

## What you'll need

| Layer | Why | Already have it? | If not |
|---|---|---|---|
| Python 3.11+ | runs the app + CLIs | `python --version` | [§1](#1-python-311) |
| pipx | installs the CLIs cleanly | `pipx --version` | [§2](#2-pipx) |
| StrataBI + StrataCTL | the product + installer | `stratabi --version` | [§3](#3-install-stratabi--stratactl) |
| An AWS account + credentials | everything deploys here | `aws sts get-caller-identity` | [§4](#4-aws-account--credentials) |
| OpenTofu (or Terraform) | stands up the data plane | `tofu -version` | [§5](#5-opentofu) |

Then: **[§6 deploy](#6-deploy-the-data-plane) → [§7 run](#7-run-stratabi) → [§8 first dashboard](#8-your-first-dashboard).**

---

## 1. Python 3.11+

**Check:** `python --version` (or `python3 --version`). If it's 3.11 or newer, skip to §2.

- **Windows:** `winget install Python.Python.3.12` — or download the installer from [python.org/downloads](https://www.python.org/downloads/) and **check "Add python.exe to PATH."**
- **macOS:** `brew install python@3.12` (needs [Homebrew](https://brew.sh)) — or the [python.org](https://www.python.org/downloads/) installer.
- **Linux (Debian/Ubuntu):** `sudo apt update && sudo apt install -y python3 python3-pip python3-venv`

> Python **3.11–3.14** all work. Installing fresh? **3.12** is the safe pick.

## 2. pipx

pipx installs command-line apps into isolated environments so they never conflict with your other Python packages. (Many people haven't used it — that's fine.)

**Check:** `pipx --version`. If it prints a version, skip to §3.

**Install (all platforms):**
```bash
python -m pip install --user pipx
python -m pipx ensurepath
```
Then **close and reopen your terminal** (so the PATH change takes effect).

- **macOS:** `brew install pipx && pipx ensurepath` also works.
- **Linux:** `sudo apt install -y pipx && pipx ensurepath`.
- Docs: [pipx.pypa.io](https://pipx.pypa.io/stable/installation/).

## 3. Install StrataBI + StrataCTL

```bash
pipx install stratabi     # the Developer Edition runtime (the app)
pipx install stratactl    # the installer/orchestrator (provisions your AWS data plane)
```

**Verify:**
```bash
stratabi --version
stratactl --version
```
Upgrade later with `pipx upgrade stratabi` / `pipx upgrade stratactl`.

---

## 4. AWS account + credentials

StrataBI deploys into **your** AWS account. You need (a) an account, (b) the AWS CLI, and (c) credentials the CLIs can use.

**Check:** run `aws sts get-caller-identity`. If it prints your Account ID and an ARN, your credentials work — **skip to §5.**

### 4a. No AWS account yet?

Create one at [aws.amazon.com](https://aws.amazon.com/) → *Create an AWS Account* (needs an email + card). StrataBI's own footprint is serverless and light, but your usage sets the bill — see the [cost FAQ](https://shaleio.com/faq.html) and estimate with the [AWS Pricing Calculator](https://calculator.aws/). Then continue below.

### 4b. Install the AWS CLI

**Check:** `aws --version`. If present, skip to 4c.

- **Windows:** download and run the MSI: [awscli.amazonaws.com/AWSCLIV2.msi](https://awscli.amazonaws.com/AWSCLIV2.msi)
- **macOS:** `brew install awscli` — or the [official pkg](https://awscli.amazonaws.com/AWSCLIV2.pkg).
- **Linux:** `curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip && unzip awscliv2.zip && sudo ./aws/install`
- Docs: [AWS CLI install guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html).

### 4c. Get credentials

**Recommended — IAM Identity Center (SSO).** Short-lived credentials, nothing
long-lived to leak. This is the best-practice path for any shared, org, or
production account.
1. In the AWS console, open **IAM Identity Center** → enable it (once per org) → create a user and assign it **AdministratorAccess** (or a scoped role) to your account.
2. On your machine:
   ```bash
   aws configure sso
   ```
   Enter the **SSO start URL** and **region** it shows in the console, pick your account + role, and give the profile a name (e.g. `stratabi`).
3. Log in: `aws sso login --profile stratabi`.

**⚡ Fast track — personal accounts only — IAM access keys.** The quickest way to
dip your toes in on your *own* personal AWS account. **Don't** use this on a shared or
production account — prefer SSO above.
1. AWS console → **IAM** → **Users** → *Create user* (e.g. `stratabi-cli`) → attach **AdministratorAccess** (or a scoped policy).
2. Select the user → **Security credentials** → **Create access key** → *Command Line Interface (CLI)* → copy the **Access key ID** and **Secret access key**.
3. On your machine:
   ```bash
   aws configure
   ```
   Paste the key ID + secret, set a default region (below), output `json`.

> **Security:** treat the secret key like a password. Prefer SSO (Path A) or a scoped IAM policy over long-lived admin keys where you can. Never commit keys or paste them into chats.

### 4d. Region

Pick the AWS region to deploy into (e.g. `us-east-1`). `aws configure` (Path B) sets a default; for SSO it's in your profile. You can always pass `--region us-east-1` to the CLI, and it's good to also set:
```bash
# Windows (cmd):  set AWS_DEFAULT_REGION=us-east-1
# macOS/Linux:    export AWS_DEFAULT_REGION=us-east-1
```

### 4e. Verify

```bash
aws sts get-caller-identity --profile stratabi   # (omit --profile if you used a default)
```
You should see your **Account ID**. That's your green light.

---

## 5. OpenTofu

`stratactl bootstrap` runs OpenTofu (or Terraform) locally to stand up the data plane. Install one.

**Check:** `tofu -version` (or `terraform -version`). If present, skip to §6.

- **Windows:** `winget install OpenTofu.Tofu` — or `scoop install opentofu`, or download the zip from [opentofu.org/docs/intro/install](https://opentofu.org/docs/intro/install/) and put `tofu.exe` on your PATH.
- **macOS:** `brew install opentofu`.
- **Linux:** `curl -fsSL https://get.opentofu.org/install-opentofu.sh | sh` (or your package manager).
- Terraform works too if you already have it — the commands are identical.

> **Bring your own** OpenTofu/Terraform — StrataCTL never forces a distribution on
> you. _(Planned: an optional auto-fetch of a pinned OpenTofu to `~/.stratactl/bin`,
> with a `--skip`/`--tofu-path` flag so you can always use your own — making this step
> "nothing to do" without taking away the choice.)_

---

## 6. Deploy the data plane

Three commands (use your profile + region). This creates a small serverless data plane (S3, Athena, Glue, DynamoDB, two Lambdas) in your account — no servers, pennies at dev scale.

```bash
stratactl --profile stratabi --region us-east-1 bootstrap --run --yes   # one-time: StrataCI
stratactl --profile stratabi --region us-east-1 dev install             # deploy the data plane
stratactl --profile stratabi --region us-east-1 dev configure-local     # write a non-secret .env
```

- **bootstrap** stands up StrataCI (the deploy runner) in your account.
- **dev install** deploys the StrataBI data plane.
- **dev configure-local** writes the `STRATABI_*` settings + your region/profile into a local `.env` (no AWS keys) so the app can find everything.

> Tip: `--profile`/`--region` can go anywhere in the command, and if you set a default AWS profile you can drop `--profile` entirely.

## 7. Run StrataBI

```bash
stratabi --check     # preflight: deps, AWS creds/region, settings — should be all [ok]
stratabi             # serves http://127.0.0.1:8050
```

Open **http://127.0.0.1:8050**. You'll land on the StrataBI home page; the **Builder** authors dashboards and the **Dashboard** page runs them.

## 8. Your first dashboard

Load a sample, or the ForgeWorks demo dataset:

```bash
# push a sample dashboard into your bucket (renders immediately)
stratactl --profile stratabi --region us-east-1 dashboards push getting-started.json

# or: load the ForgeWorks synthetic dataset + an Athena-backed dashboard
stratactl --profile stratabi --region us-east-1 dev demo install
```

Refresh the app — your dashboard is live.

---

## Uninstall — remove everything

Everything lives in your account, so teardown is clean and complete:

```bash
stratactl --profile stratabi --region us-east-1 dev demo remove     # if you loaded ForgeWorks
stratactl --profile stratabi --region us-east-1 dev uninstall       # destroy the StrataBI data plane
stratactl --profile stratabi --region us-east-1 bootstrap --destroy # destroy StrataCI itself
```

`bootstrap --destroy` pulls StrataCI's state from your bucket (`bootstrap` saved it
there) and tears it down locally, so nothing depends on the machine that installed it.
Between those two commands, StrataBI leaves no resources behind.

## Troubleshooting

- Re-run `stratabi --check` — it names any missing setting.
- `stratactl doctor` *(coming)* will check every layer (Python, AWS CLI, creds, region, OpenTofu, network) and tell you exactly how to fix each.
- Common ones: `NoRegionError` → set `AWS_DEFAULT_REGION`; `unable to locate credentials` → `aws sso login` or `aws configure`; `tofu: not found` → §5.
