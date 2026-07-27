# Changelog — StrataBI Developer Edition

All notable changes. Versions follow `stratabi/__init__.py`.

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
