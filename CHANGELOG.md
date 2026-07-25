# Changelog — StrataBI Developer Edition

All notable changes. Versions follow `stratabi/__init__.py`.

## [Unreleased]

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
