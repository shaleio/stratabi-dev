"""stratabi-dev CLI: --version/--help/--check must work without AWS or Dash present."""

import subprocess
import sys


def _run(*args):
    return subprocess.run([sys.executable, "-m", "stratabi.cli", *args],
                          capture_output=True, text=True)


def test_version():
    r = _run("--version")
    assert r.returncode == 0
    assert "stratabi-dev" in (r.stdout + r.stderr)


def test_help_lists_flags():
    r = _run("--help")
    assert r.returncode == 0
    for flag in ("--host", "--port", "--debug", "--check"):
        assert flag in r.stdout


def test_check_reports_and_exits_nonzero_without_env():
    # With no AWS/STRATABI_* config, --check should FAIL gracefully (exit 1),
    # not crash, and must print actionable guidance.
    r = _run("--check")
    assert r.returncode == 1
    assert "STRATABI_" in r.stdout or "AWS" in r.stdout
