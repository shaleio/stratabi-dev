# Changelog — StrataBI Developer Edition

All notable changes. Versions follow `stratabi/__init__.py`.

## [1.7.4] — 2026-11-08

Fixes from the 1.7.3 retest (N11–N18), completing the partials from 1.7.3.

### Fixed
- **N7/N12 — the app now starts with only `AWS_REGION` set, and `import stratabi.core.runner`
  works without a region.** All import-time boto3 clients/resources (runner, status_store,
  lambda_runner, s3_loader, source_macros, app) are now created lazily with an explicit
  region, and the CLI normalizes `AWS_REGION → AWS_DEFAULT_REGION` before importing the app.
- **N11 — a failing tile shows the error instead of a blank 500.** `update_tile` catches
  execution exceptions and renders them (friendly text for missing/expired credentials),
  recording FAILED.
- **N15 — `table` blocks render with no config.** The AG Grid id defaults to a stable
  per-tile id instead of `None` (which Dash rejected); `grid_id` is now allowed by the schema.
- **N17 — the download button works for async Athena/Lambda tiles**, presigning the
  latest SUCCEEDED result; it now shows by default only where an artifact exists (cache
  and async tiles).
- **N18 — the download modal's Close button now closes it.**
- **N14 — async tiles no longer stick on "Processing…".** Dashboards with any async tile
  auto-enable status polling (5s) regardless of `interval_enabled`.
- **N4 — the demo "most delayed orders" gradient now actually appears** (bumped the demo
  cache version so the regenerated data ships).

### Changed
- **N16 — the Builder's Save now runs the same schema validation as the CLI** and warns
  (with the first error) when a dashboard won't pass `dashboards push`.
- Docs/schema: `depends_on` marked reserved; `interval_enabled` notes async auto-polling.

## [1.7.3] — 2026-11-08

Fixes from the 1.7.2 retest (Linux no-AWS, and Windows against live Athena).

### Fixed
- **N8 — parameterised tiles no longer 500 on first load.** A filtered tile ran before
  the input store was populated and raised "Missing input for SQL param". The tile now
  seeds input defaults from each `input_select`/`input_range` block's `value` on load,
  and shows "Waiting for input…" instead of raising when a value isn't available yet.
- **N1 — demo dashboard no longer throws a 500 from the status poller.** The poller hit
  DynamoDB in local mode (`NoCredentialsError`); it now returns early when `MODE=local`.
- **N7 — `import stratabi.core.runner` works without a region.** The Lambda client and
  module-registry table are created lazily instead of at import time.
- **N6 — the bundled LLM contract no longer leaks a foreign account or a placeholder
  URL.** Examples use `<your-system-bucket>` (substituted with `STRATABI_SYSTEM_BUCKET`
  at assembly time), and the schema link points at the real schema URL.

### Changed
- **N2** — in local/demo mode the startup log says `mode=local (demo)` instead of
  printing `STRATABI_SYSTEM_BUCKET=None`.
- **N3** — markdown-block tables (e.g. the demo "Key metrics" tile) get cell padding so
  labels and values no longer collide.
- **N4** — demo "days late" uses a skewed 1–30 spread so "most delayed orders" shows a
  gradient instead of every row tying at 9.
- **N9/N10** — `depends_on` marked reserved/not-enforced (schema + docs); the LLM
  contract now tells the model to set `triggered_by` on input-bound tiles.

## [1.7.2] — 2026-11-07

Fixes from a first-time new-user install test (pipx, Windows + Linux).

### Fixed
- **`.env` is now loaded when installed via pipx/pip.** `load_dotenv()` searched from
  the installed package directory (site-packages), so a `.env` in the user's working
  directory was ignored and `--check` reported missing `STRATABI_*` even when the file
  was correct. Both the CLI and the app now use `find_dotenv(usecwd=True)`, and
  `--check` prints which `.env` it loaded (or "none found in <cwd>").
- **`stratabi demo quick` (no-AWS demo) now shows its dashboard.** The dashboard/builder
  pickers always read from S3; in local mode they now read the on-disk demo dashboard
  directory, so the ForgeWorks demo lists and renders with no AWS configured.
- **Builder → "LLM Contract" no longer crashes.** Restored `load_core_contract()` /
  `load_local_schema_text()` (and the missing module `logger`) in `ai_helpers`, and the
  core LLM contract (`data/docs/llm_contract.txt`) now ships in the wheel.
- Fixed an undefined `get_s3_client` reference in `loader.load_dashboards_s3`.

### Changed
- Monaco editor assets are no longer auto-injected on every page (`assets_ignore`),
  eliminating the `define is not defined` console spam and duplicate worker definitions;
  the editor loads only on the Builder via its own loader.
- `--check` polish: each fix hint prints under its own line, aligned status tags, says
  when the region defaults to `us-east-1`, links the docs, and fixes the install hint
  (`stratabi`, not `stratabi-dev`). New `--check --online` runs `sts:GetCallerIdentity`
  and `s3:HeadBucket` on the system bucket.

### CI
- Added a gating `ruff --select F821` (undefined-name) lint and a Windows smoke job to
  the release workflow.

## [1.7.1] — 2026-11-06

### Security
- **Closed a remote-code-execution footgun in `python -m stratabi.app`.** The
  `__main__` block ran the dev server with `debug=True` on `0.0.0.0`, which exposes
  the Werkzeug interactive debugger (arbitrary code execution) on every interface.
  It now binds `127.0.0.1` with debug **off**, matching the `stratabi` CLI; opt in
  per-env with `STRATABI_HOST` / `STRATABI_DEBUG`. The supported entry point remains
  the `stratabi` command.
- **`raw_html` block now sandboxes its iframe** (`sandbox="allow-scripts allow-popups"`,
  omitting `allow-same-origin`) so embedded scripts run in a null origin and cannot
  reach the app's cookies/localStorage. Override per block via `sandbox` (or `null`
  to opt out). Brings the community block in line with the enterprise runtime.

### Changed
- All dev-server launch paths (`stratabi`, `stratabi demo quick`, and the
  `stratabi.app` `__main__` fallback) now run the Flask server with `threaded=True`
  so a slow tile no longer blocks concurrent requests from the same browser.

### Changed (parity with enterprise runtime)
- Plotly and Plotly-resampler blocks now hide the Plotly logo (`displaylogo: false`)
  and show the mode bar on hover instead of always, matching the enterprise blocks.
- Responsive navbar: collapses to a hamburger below the `md` breakpoint so the app
  is usable in a narrow/portrait browser window (e.g. a tool opening `127.0.0.1`).

### Docs
- Reworked the architecture diagram (README) to drop the box verticals, which PyPI's
  web font rendered at a different width and misaligned. Now uses horizontal rules only.

## [1.0.3] — 2026-08-02

### Added
- **Quickstart** in the README: a 0-to-dashboard walkthrough (install → `--check`
  → `stratactl dev install` → `stratabi dashboards push`).
- Guidance on **`pipx` vs `pip`** for installing the Developer Edition, and how to
  uninstall the data plane via `bootstrap --destroy`.

### Changed
- README now points to the website Installation Guide as the canonical source;
  removed the superseded `QUICKSTART.md`.

## [1.0.2] — 2026-07-29

### Added
- Developer Edition **splash page** at `/` (`pages/home.py`): orients a developer
  and links to the Builder and Dashboard; the navbar logo now links home.
- **`stratabi dashboards {push,ls,rm}`** — a thin, AWS-native funnel that validates a
  dashboard against the packaged schema and uploads it to `analyst/dashboards/`.
  Added `jsonschema` dependency.
- Sample dashboards under `samples/dashboards/` (a static one and an Athena template).

### Fixed
- **Default dashboard renders again**: rewrote `infra/bootstrap/default.json` to the
  current schema (`block:{type,config}`, `position:{row,order,width}`) — the old shape
  was silently skipped by the renderer.
- Navbar "Builder" link pointed at the empty root (`/`); now points at `/builder`.
- Quieted werkzeug's per-request access log (override with `STRATABI_ACCESS_LOG=1`).

## [1.0.1] — 2026-07-26

### Fixed
- Resolve the navbar logo (and packaged assets) relative to the package rather than the
  working directory — fixes a startup crash after `pipx install` (`stratabi/assets/logo.png`
  not found when launched from outside the repo root).
- Use absolute imports in the `pages/` modules so Dash `use_pages` no longer raises
  "attempted relative import beyond top-level package" on an installed package.
- `build_module_bundle.py` ships the full `infra/` tree into the bundle's `tofu/`
  (Lambda sources, prebuilt Lambda/layer archives, seed JSON) so the StrataCI runner's
  `tofu plan` resolves every `${path.module}` file reference.

### Changed
- CLI help/hint text refers to the `stratabi` command (dropped stale `stratabi-dev`
  references).

## [1.0.0] — 2026-07-26

### Added
- `pyproject.toml` — pipx-installable as `stratabi-dev`; console script
  `stratabi-dev`; dynamic version; custom source-available license metadata (SGCL v1.0).
- `stratabi/cli.py` entrypoint: `--help`, `--version`, `--host` (loopback default),
  `--port`, `--debug` (off by default), `--check` preflight. `/healthz` retained.
- `build_module_bundle.py` — deterministic data-plane module bundle + SHA-256 +
  release manifest; resolves the theme-path coupling inside the bundle.
- `bundle/stratabi-module.json` runner manifest (data-plane, first-party permissions).
- `SECURITY.md`, `CONTRIBUTING.md` (SGCL-aligned), release CI scaffold.

### Changed
- README rewritten to lead with the SGCL notice, pipx + manual paths, cost/support
  notices, and the CLI.
- Dependencies split: local-runtime deps only in the default install; heavy Lambda/
  build libs (awswrangler, scikit-learn, fastparquet, numpy) moved to a `[lambda]` extra.

### Licensing
- Placed the authoritative SGCL v1.0 as `LICENSE.md` (+ canonical `LICENSE.docx`);
  removed the obsolete v0.3 draft.

### Housekeeping
- `.gitignore` now excludes `terraform.tfvars`/`*.auto.tfvars` and packaging caches.
