# Changelog — StrataBI Developer Edition

All notable changes. Versions follow `stratabi/__init__.py`.

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
