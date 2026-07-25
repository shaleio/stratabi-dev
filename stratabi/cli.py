"""StrataBI Developer Edition command-line entry point.

Installed as the ``stratabi-dev`` console script (see pyproject.toml). Running
``stratabi-dev`` with no arguments starts the local Dash app on a safe default
host/port. ``--version``, ``--help`` and ``--check`` are handled WITHOUT importing
the app package, so they never trigger the app's import-time AWS clients.

    stratabi-dev                 # run on http://127.0.0.1:8050
    stratabi-dev --check         # validate environment/config, then exit
    stratabi-dev --host 0.0.0.0 --port 8060 --debug
    stratabi-dev --version
"""

from __future__ import annotations

import argparse
import os
import sys

# Version is read from the package __init__ without importing the heavy app module.
try:
    from stratabi import __version__ as _VERSION
except Exception:  # pragma: no cover - packaging edge
    _VERSION = "0.0.0"

# The STRATABI_* settings the runtime needs to reach a real data plane. These come
# from `tofu output` after `stratactl dev install` (or a manual `tofu apply`).
_REQUIRED_ENV = [
    "STRATABI_SYSTEM_BUCKET",
    "STRATABI_DASHBOARD_PREFIX",
    "STRATABI_ATHENA_OUTPUT",
    "STRATABI_CATALOG_DATABASE",
]


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stratabi-dev",
        description="StrataBI Developer Edition — local BI runtime "
        "(source-available under the Shaleio Guild Community License v1.0).",
    )
    p.add_argument("--version", action="version", version=f"stratabi-dev {_VERSION}")
    # Bind to loopback by default — this is a local developer tool, not a hosted
    # service. Use --host 0.0.0.0 explicitly (e.g. inside a WorkSpaces desktop).
    p.add_argument("--host", default="127.0.0.1",
                   help="Interface to bind (default: 127.0.0.1, loopback only).")
    p.add_argument("--port", type=int, default=8050, help="Port (default: 8050).")
    p.add_argument("--debug", action="store_true",
                   help="Enable Dash debug mode (off by default).")
    p.add_argument("--check", action="store_true",
                   help="Validate environment/config and dependencies, then exit.")

    sub = p.add_subparsers(dest="command")  # optional; no command = run the app

    demo = sub.add_parser("demo", help="ForgeWorks synthetic demonstration.")
    dsub = demo.add_subparsers(dest="demo_action", required=True)
    dq = dsub.add_parser("quick", help="Open the ForgeWorks Quick Demo (embedded, no AWS).")
    dq.add_argument("--host", default="127.0.0.1")
    dq.add_argument("--port", type=int, default=8050)
    dq.add_argument("--debug", action="store_true")
    dq.add_argument("--no-launch", action="store_true",
                    help="Generate the demo but don't start the server.")
    dsub.add_parser("generate", help="Generate the Quick Demo assets (no launch).")
    dsub.add_parser("status", help="Show demo status.")
    drl = dsub.add_parser("remove-local", help="Remove local Quick Demo assets.")
    drl.add_argument("--yes", action="store_true")

    # AWS demo (isolated namespace in your data plane). Also available via
    # `stratactl dev demo …`. Kept as a nested group to preserve the local/AWS split.
    daws = dsub.add_parser("aws", help="AWS-backed ForgeWorks demo (Athena).")
    asub = daws.add_subparsers(dest="aws_action", required=True)
    for act in ("install", "remove", "status"):
        ap = asub.add_parser(act)
        ap.add_argument("--profile", default=None)
        ap.add_argument("--region", default=None)
        ap.add_argument("--yes", action="store_true")
    return p


def _demo(args) -> int:
    from stratabi import demo
    action = args.demo_action
    if action == "generate":
        meta = __import__("stratabi.demo.quick", fromlist=["x"]).generate_demo(force=True)
        print(f"generated ForgeWorks Quick Demo → {meta['dashboard_path']}")
        print(f"rows: {meta['rows']}")
        return 0
    if action == "status":
        import json
        from stratabi.demo import quick
        print(json.dumps(quick.status(), indent=2))
        return 0
    if action == "remove-local":
        from stratabi.demo import quick
        if not getattr(args, "yes", False):
            if (input(f"Remove local demo cache at {demo.cache_dir()}? [y/N] ")
                    .strip().lower() not in ("y", "yes")):
                print("aborted."); return 0
        removed = quick.remove_local()
        print(f"removed {len(removed)} files.")
        return 0
    if action == "quick":
        from stratabi.demo import quick
        meta = quick.generate_demo()
        print(f"ForgeWorks Quick Demo — {demo.SYNTHETIC_NOTICE}")
        print(f"  dashboard: {meta['dashboard_path']}")
        if getattr(args, "no_launch", False):
            return 0
        import os
        os.environ.update(quick.launch_env())
        try:
            from stratabi.app import app
        except Exception as exc:  # noqa: BLE001
            print(f"generated the demo, but the app could not start: {exc}")
            print("Run `stratabi-dev --check` to diagnose, then `stratabi-dev`.")
            return 1
        url = f"http://{args.host}:{args.port}"
        print(f"  serving on {url}  (Ctrl-C to stop)")
        app.run(host=args.host, port=args.port, debug=args.debug)
        return 0
    if action == "aws":
        return _demo_aws(args)
    return 2


def _demo_aws(args) -> int:
    import boto3
    from stratabi.demo import athena, cleanup
    session = boto3.Session(profile_name=getattr(args, "profile", None),
                            region_name=getattr(args, "region", None))
    act = args.aws_action
    try:
        if act == "install":
            athena.install(session, profile=args.profile, confirm=not args.yes)
        elif act == "remove":
            cleanup.remove_aws(session, profile=args.profile, confirm=not args.yes)
        elif act == "status":
            import json
            cfg = athena.discover(session, profile=args.profile)
            print(json.dumps(athena.plan(cfg), indent=2))
    except athena.DemoError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _load_env() -> None:
    """Load a local .env (dev convenience) if python-dotenv is available."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass


def _check() -> int:
    """Lightweight preflight: dependencies, AWS credential/region presence, and the
    required STRATABI_* settings. Never makes a network call; reports actionably."""
    _load_env()
    ok = True

    print(f"stratabi-dev {_VERSION}")

    # 1) Core runtime imports (surfaces a broken/thin install clearly).
    try:
        import dash  # noqa: F401
        import plotly  # noqa: F401
        import pandas  # noqa: F401
        print("  [ok]  runtime dependencies import (dash, plotly, pandas)")
    except Exception as exc:
        ok = False
        print(f"  [FAIL] runtime dependency import failed: {exc}")
        print("         fix: pipx install 'stratabi-dev'  (or pip install -e .)")

    # 2) AWS credentials + region (via the standard provider chain; no API call).
    try:
        import botocore.session
        sess = botocore.session.get_session()
        region = sess.get_config_variable("region") or os.getenv("AWS_REGION") \
            or os.getenv("AWS_DEFAULT_REGION")
        creds = sess.get_credentials()
        print(f"  [{'ok' if region else 'FAIL'}]  AWS region: {region or '(unset)'}")
        print(f"  [{'ok' if creds else 'FAIL'}]  AWS credentials: "
              f"{'found via provider chain' if creds else 'NOT found'}")
        ok = ok and bool(region) and bool(creds)
        if not region:
            print("         fix: set AWS_REGION (or AWS_PROFILE) in your environment/.env")
        if not creds:
            print("         fix: configure an AWS profile or export AWS_ACCESS_KEY_ID/…")
    except Exception as exc:
        ok = False
        print(f"  [FAIL] could not evaluate AWS configuration: {exc}")

    # 3) Required data-plane settings.
    missing = [k for k in _REQUIRED_ENV if not os.getenv(k)]
    if missing:
        ok = False
        print(f"  [FAIL] missing STRATABI_* settings: {', '.join(missing)}")
        print("         fix: run `stratactl dev install` (or `tofu apply` in infra/) and")
        print("              write the outputs into your .env (see README).")
    else:
        print("  [ok]  required STRATABI_* settings present")

    print("PASS" if ok else "FAIL — resolve the items above before running.")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if getattr(args, "command", None) == "demo":
        _load_env()
        return _demo(args)

    if args.check:
        return _check()

    _load_env()
    # Import the app only on the run path — this is where the app's import-time AWS
    # clients are created. Turn a missing region/credentials into an actionable
    # message instead of a raw stack trace.
    try:
        from stratabi.app import app
    except Exception as exc:  # noqa: BLE001
        name = type(exc).__name__
        print(f"error: could not start StrataBI Dev ({name}): {exc}", file=sys.stderr)
        print("hint: run `stratabi-dev --check` to see what's missing "
              "(usually AWS_REGION / credentials / STRATABI_* settings).",
              file=sys.stderr)
        return 1

    url = f"http://{args.host}:{args.port}"
    print(f"StrataBI Developer Edition {_VERSION}")
    print(f"  serving on {url}  (Ctrl-C to stop)")
    if args.host == "0.0.0.0":
        print("  note: bound to 0.0.0.0 — reachable from your network. This is a "
              "developer tool with no built-in auth; do not expose it publicly.")
    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
