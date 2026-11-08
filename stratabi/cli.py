"""StrataBI Developer Edition command-line entry point.

Installed as the ``stratabi`` console script (see pyproject.toml). Running
``stratabi`` with no arguments starts the local Dash app on a safe default
host/port. ``--version``, ``--help`` and ``--check`` are handled WITHOUT importing
the app package, so they never trigger the app's import-time AWS clients.

    stratabi                 # run on http://127.0.0.1:8050
    stratabi --check         # validate environment/config, then exit
    stratabi --host 0.0.0.0 --port 8060 --debug
    stratabi --version
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
        prog="stratabi",
        description="StrataBI Developer Edition — local BI runtime "
        "(source-available under the Shaleio Guild Community License v1.0).",
    )
    p.add_argument("--version", action="version", version=f"stratabi {_VERSION}")
    # Bind to loopback by default — this is a local developer tool, not a hosted
    # service. Use --host 0.0.0.0 explicitly (e.g. inside a WorkSpaces desktop).
    p.add_argument("--host", default="127.0.0.1",
                   help="Interface to bind (default: 127.0.0.1, loopback only).")
    p.add_argument("--port", type=int, default=8050, help="Port (default: 8050).")
    p.add_argument("--debug", action="store_true",
                   help="Enable Dash debug mode (off by default).")
    p.add_argument("--check", action="store_true",
                   help="Validate environment/config and dependencies, then exit.")
    p.add_argument("--online", action="store_true",
                   help="With --check: also make live AWS calls (sts:GetCallerIdentity, "
                        "s3:HeadBucket on the system bucket).")

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

    # Dashboards funnel — validate + push JSON into analyst/dashboards/ in your bucket
    # (AWS-native; the app loads dashboards from S3 in STRATABI_MODE=aws).
    dash = sub.add_parser("dashboards",
                          help="Manage dashboards in your system bucket (analyst/dashboards/).")
    dashsub = dash.add_subparsers(dest="dash_action", required=True)
    dpush = dashsub.add_parser("push", help="Validate + upload dashboard JSON to S3.")
    dpush.add_argument("paths", nargs="+",
                       help="Dashboard .json file(s), or a directory of them.")
    dpush.add_argument("--name", default=None,
                       help="Override the stored name (single file only). e.g. --name default")
    dashsub.add_parser("ls", help="List dashboards in the system bucket.")
    drm = dashsub.add_parser("rm", help="Remove a dashboard by name.")
    drm.add_argument("name", help="Dashboard name (with or without .json).")
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
            print("Run `stratabi --check` to diagnose, then `stratabi`.")
            return 1
        url = f"http://{args.host}:{args.port}"
        print(f"  serving on {url}  (Ctrl-C to stop)")
        app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
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


def _load_env() -> str | None:
    """Load a local .env from the CURRENT working directory if present.

    Returns the path of the .env that was loaded, or None.

    Note: bare ``load_dotenv()`` resolves the file by walking up from the *calling
    module's* directory — which, for a pipx/pip install, is site-packages, not the
    user's project folder. We force the search to start at the cwd so the documented
    "write .env, then run stratabi here" flow actually works when installed.
    """
    path = None
    try:
        from dotenv import load_dotenv, find_dotenv
    except Exception as exc:  # python-dotenv not installed
        print(f"note: python-dotenv unavailable, not loading .env ({exc})", file=sys.stderr)
    else:
        path = find_dotenv(usecwd=True)
        if path:
            load_dotenv(path)
    _normalize_region()
    return path


def _normalize_region() -> None:
    """Mirror AWS_REGION -> AWS_DEFAULT_REGION when only the former is set. botocore
    versions differ on which they read for implicit region resolution, so a .env (or
    shell) that sets only AWS_REGION could pass `--check` yet leave boto3 clients created
    at import with no region. Runs before the app is imported. See N12."""
    if os.getenv("AWS_REGION") and not os.getenv("AWS_DEFAULT_REGION"):
        os.environ["AWS_DEFAULT_REGION"] = os.environ["AWS_REGION"]


_DOCS_URL = "https://shaleio.com/docs/developer-edition"


def _tag(flag: bool) -> str:
    # Fixed-width status tags so the text after them lines up: both are 6 chars.
    return "[ok]  " if flag else "[FAIL]"


def _check(online: bool = False) -> int:
    """Lightweight preflight: dependencies, AWS credential/region presence, and the
    required STRATABI_* settings. No network calls unless --online; reports actionably."""
    env_path = _load_env()
    ok = True

    print(f"stratabi {_VERSION}")
    print(f"  {'[ok]  ' if env_path else '[--]  '} .env: "
          f"{env_path if env_path else f'none found in {os.getcwd()}'}")

    # 1) Core runtime imports (surfaces a broken/thin install clearly).
    try:
        import dash  # noqa: F401
        import plotly  # noqa: F401
        import pandas  # noqa: F401
        print(f"  {_tag(True)} runtime dependencies import (dash, plotly, pandas)")
    except Exception as exc:
        ok = False
        print(f"  {_tag(False)} runtime dependency import failed: {exc}")
        print("         fix: pipx install stratabi   (or `pip install -e .` in a checkout)")

    # 2) AWS credentials + region (via the standard provider chain). Each hint prints
    #    directly under its own line.
    region = None
    try:
        import botocore.session
        sess = botocore.session.get_session()
        region = sess.get_config_variable("region") or os.getenv("AWS_REGION") \
            or os.getenv("AWS_DEFAULT_REGION")
        # Region is not hard-required: the runtime defaults to us-east-1. Report it as a
        # note, not a failure, but say it's a fallback.
        if region:
            print(f"  {_tag(True)} AWS region: {region}")
        else:
            print("  [--]   AWS region: (unset) — the app will default to us-east-1")
            print("         set AWS_REGION (or AWS_PROFILE) to choose a region explicitly")

        creds = sess.get_credentials()
        if creds:
            print(f"  {_tag(True)} AWS credentials: found via provider chain")
        else:
            ok = False
            print(f"  {_tag(False)} AWS credentials: NOT found")
            print("         fix: configure an AWS profile or SSO, or export "
                  "AWS_ACCESS_KEY_ID/… (temporary STS creds work)")
    except Exception as exc:
        ok = False
        print(f"  {_tag(False)} could not evaluate AWS configuration: {exc}")

    # 3) Required data-plane settings.
    missing = [k for k in _REQUIRED_ENV if not os.getenv(k)]
    if missing:
        ok = False
        print(f"  {_tag(False)} missing STRATABI_* settings: {', '.join(missing)}")
        print("         fix: run `stratactl dev install` (or `tofu apply` in infra/), then")
        print(f"              append the outputs to your .env. Variable reference: {_DOCS_URL}")
    else:
        print(f"  {_tag(True)} required STRATABI_* settings present")

    # 4) Optional live AWS checks.
    if online:
        ok = _check_online(region) and ok

    print(("PASS 🐒🔨" if ok
           else f"FAIL — resolve the items above before running. Docs: {_DOCS_URL}"))
    return 0 if ok else 1


def _check_online(region: str | None) -> bool:
    """Live AWS reachability checks (only run under `--check --online`): confirm the
    credentials actually work and the system bucket is reachable."""
    try:
        import boto3
    except Exception as exc:
        print(f"  {_tag(False)} --online: boto3 unavailable: {exc}")
        return False

    ok = True
    kwargs = {"region_name": region} if region else {}

    try:
        ident = boto3.client("sts", **kwargs).get_caller_identity()
        print(f"  {_tag(True)} sts:GetCallerIdentity -> account {ident.get('Account')}")
    except Exception as exc:
        ok = False
        print(f"  {_tag(False)} sts:GetCallerIdentity failed: {exc}")

    bucket = os.getenv("STRATABI_SYSTEM_BUCKET")
    if bucket:
        try:
            boto3.client("s3", **kwargs).head_bucket(Bucket=bucket)
            print(f"  {_tag(True)} s3:HeadBucket {bucket}")
        except Exception as exc:
            ok = False
            print(f"  {_tag(False)} s3:HeadBucket {bucket} failed: {exc}")
    return ok


def _dashboards(args) -> int:
    from stratabi import dashboards_admin as da
    action = args.dash_action
    if action == "push":
        return da.push(args.paths, name=getattr(args, "name", None))
    if action == "ls":
        return da.ls()
    if action == "rm":
        return da.rm(args.name)
    return 1


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if getattr(args, "command", None) == "dashboards":
        _load_env()
        from stratabi.dashboards_admin import DashboardError
        try:
            rc = _dashboards(args)
        except DashboardError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if rc == 0 and args.dash_action in ("push", "rm"):
            print("done 🐒🔨")
        return rc

    if getattr(args, "command", None) == "demo":
        _load_env()
        rc = _demo(args)
        # Brand sign-off on completed demo ops. Skip `quick` (it launches the server
        # and only returns on Ctrl-C, where a trailing "done" would read oddly).
        if rc == 0 and getattr(args, "demo_action", None) != "quick":
            print("done 🐒🔨")   # Shaleio / MonkeyHammer
        return rc

    if args.check:
        return _check(online=getattr(args, "online", False))

    _load_env()
    # Import the app only on the run path — this is where the app's import-time AWS
    # clients are created. Turn a missing region/credentials into an actionable
    # message instead of a raw stack trace.
    try:
        from stratabi.app import app
    except Exception as exc:  # noqa: BLE001
        name = type(exc).__name__
        print(f"error: could not start StrataBI Dev ({name}): {exc}", file=sys.stderr)
        print("hint: run `stratabi --check` to see what's missing "
              "(usually AWS_REGION / credentials / STRATABI_* settings).",
              file=sys.stderr)
        return 1

    url = f"http://{args.host}:{args.port}"
    print(f"StrataBI Developer Edition {_VERSION}")
    print(f"  serving on {url}  (Ctrl-C to stop)")
    if args.host == "0.0.0.0":
        print("  note: bound to 0.0.0.0 — reachable from your network. This is a "
              "developer tool with no built-in auth; do not expose it publicly.")
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
