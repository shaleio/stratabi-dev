#!/usr/bin/env python3
"""Build the StrataBI Developer Edition module bundle consumed by StrataCI.

Assembles a CLEAN, deterministic ``stratabi_dev-<version>-module.zip`` from tracked
source files only, plus a SHA-256 checksum and a release manifest. Nothing is
committed — run this in CI (or locally) and attach the outputs to a GitHub release.

Bundle layout (conforms to the runner manifest schema; see bundle/stratabi-module.json):

    stratabi_dev-<version>-module.zip
    ├── stratabi-module.json      # runner manifest (module_id/version/state_key/…)
    ├── LICENSE.md                # SGCL v1.0
    ├── README.md
    ├── config/config.json
    ├── tofu/                     # the data-plane OpenTofu (from infra/, cleaned)
    └── stratabi/themes/          # theme assets, so tofu's ${path.module}/../stratabi/themes resolves

Determinism: files are added in sorted order with a fixed timestamp, so the same
inputs produce a byte-identical zip (stable SHA-256).

Usage:
    python build_module_bundle.py [--out dist] [--version X.Y.Z]

Signing (documented, not performed here — no keys are created or committed):
    Official releases are signed by Shaleio. After building, the release pipeline
    signs the *release manifest* (which pins the zip's SHA-256) with the Shaleio
    release key; the detached signature is published next to the zip. The StrataCI
    runner verifies SHA-256 always, and the signature when STRATA_REQUIRE_SIGNATURE
    is set (see stratactl runner). Custom/unsigned URLs must be installed with an
    explicit --allow-unsigned and are never treated as official.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIXED_TS = (1980, 1, 1, 0, 0, 0)  # zip epoch — deterministic mtime

# Files/dirs copied into the bundle: (source relative to repo root, dest in bundle).
INCLUDE_FILES = [
    ("bundle/stratabi-module.json", "stratabi-module.json"),
    ("LICENSE.md", "LICENSE.md"),
    ("README.md", "README.md"),
    ("config.json", "config/config.json"),
]
# Directory trees copied RECURSIVELY with structure preserved: (source dir, dest prefix).
# The whole data-plane `infra/` tree ships as `tofu/` — not only the .tf files but the
# Lambda sources, the prebuilt Lambda/layer .zip artifacts, and the seed JSON that the
# tofu references via ${path.module}/lambda|build|bootstrap. Anything matching EXCLUDE
# is dropped. Themes ship too, so ${path.module}/../stratabi/themes resolves.
INCLUDE_TREES = [
    ("infra", "tofu"),
    ("stratabi/themes", "stratabi/themes"),
]
# Never bundle these (matched against the path RELATIVE to each tree root). Note: we do
# NOT exclude *.zip — the awswrangler Lambda layer and the prebuilt Lambda archives are
# REQUIRED runtime inputs. We drop local provider cache + lock (the runner runs its own
# `tofu init` on linux, so a host-generated lock would fail checksum verification),
# state, local tfvars, and junk.
EXCLUDE = re.compile(
    r"(^|/)\.terraform|\.tfstate|(^|/)terraform\.tfvars|(^|/)__pycache__(/|$)|(^|/)\.git")


def _version() -> str:
    txt = (ROOT / "stratabi" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', txt)
    return m.group(1) if m else "0.0.0"


def _collect() -> list[tuple[Path, str]]:
    items: list[tuple[Path, str]] = []
    for src, dest in INCLUDE_FILES:
        p = ROOT / src
        if not p.is_file():
            raise SystemExit(f"error: required bundle file missing: {src}")
        items.append((p, dest))
    for src_dir, dest_prefix in INCLUDE_TREES:
        base = ROOT / src_dir
        if not base.is_dir():
            raise SystemExit(f"error: required bundle dir missing: {src_dir}")
        for p in sorted(base.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(base).as_posix()
            if EXCLUDE.search(rel):
                continue
            items.append((p, f"{dest_prefix}/{rel}"))
    # De-dupe by dest, keep sorted for determinism.
    seen: dict[str, Path] = {}
    for p, dest in items:
        seen[dest] = p
    return [(p, dest) for dest, p in sorted(seen.items())]


def build(out_dir: Path, version: str) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"stratabi_dev-{version}-module.zip"
    items = _collect()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for src, dest in items:
            zi = zipfile.ZipInfo(dest, date_time=FIXED_TS)
            zi.external_attr = 0o644 << 16
            zf.writestr(zi, src.read_bytes())

    data = zip_path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    (out_dir / f"{zip_path.name}.sha256").write_text(f"{sha}  {zip_path.name}\n")

    manifest = {
        "module_id": "stratabi_dev",
        "version": version,
        "artifact": zip_path.name,
        "sha256": sha,
        "bytes": len(data),
        "files": [dest for _, dest in items],
        "signature": None,  # filled by the signing step (release pipeline)
        "signed": False,
    }
    (out_dir / f"stratabi_dev-{version}-release.json").write_text(
        json.dumps(manifest, indent=2) + "\n")

    print(f"built  {zip_path}")
    print(f"sha256 {sha}")
    print(f"files  {len(items)}")
    print(f"manifest {out_dir / f'stratabi_dev-{version}-release.json'}")
    print("NOTE: unsigned. The release pipeline signs the release manifest; see module docstring.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the StrataBI Dev module bundle.")
    ap.add_argument("--out", default="dist", help="Output directory (default: dist).")
    ap.add_argument("--version", default=None, help="Override version (default: stratabi.__version__).")
    a = ap.parse_args(argv)
    return build(ROOT / a.out if not Path(a.out).is_absolute() else Path(a.out),
                 a.version or _version())


if __name__ == "__main__":
    raise SystemExit(main())
