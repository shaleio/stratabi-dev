"""The Developer Edition is a dashboard + app playground. Enterprise surfaces stay out:
no favorites/pins/git-registry toolbar, no RBAC, no sign-in, no workspace home, no direct
AI integration (developers bring their own agent; the contract + schema ship for that)."""
import pathlib
import re

PKG = pathlib.Path(__file__).resolve().parents[1] / "stratabi"
ENTERPRISE_MODULES = ("core.auth", "core.rbac", "core.runtime_settings", "core.apps_catalog",
                      "core.workspace", "core.templates", "core.drafts", "core.demo_apps", "pages.admin")
# UI surfaces (pages, navbar, app shell) must not expose these.
UI_SYMBOLS = ("put_dashboard_favorite", "is_dashboard_favorite", "is_dashboard_pinned",
              "is_dashboard_git_registered", "dashboard-favorite-button", "dashboard-git-button", "rbac.")


def _sources():
    for p in PKG.rglob("*.py"):
        if "__pycache__" not in p.parts:
            yield p, p.read_text(encoding="utf-8")


def test_no_enterprise_modules_shipped_or_imported():
    for mod in ENTERPRISE_MODULES:
        assert not (PKG / (mod.replace(".", "/") + ".py")).exists(), mod
    for p, src in _sources():
        for mod in ENTERPRISE_MODULES:
            assert not re.search(rf"stratabi\.{re.escape(mod)}\b|from stratabi\.core import {mod.split('.')[-1]}\b", src), (p, mod)


# Enterprise-only data surfaces: nothing in the package may read or write them.
DATA_SYMBOLS = ("STRATABI_DASHBOARD_RECENTS", "STRATABI_DASHBOARD_FAVORITES", "STRATABI_DASHBOARD_PINNED",
                "record_dashboard_recent", "STRATABI_DASHBOARD_TEMPLATES")


def test_no_enterprise_data_surfaces():
    for p, src in _sources():
        for sym in DATA_SYMBOLS:
            assert sym not in src, (p.relative_to(PKG), sym)


def test_no_enterprise_ui_or_ai_calls():
    for p, src in _sources():
        rel = p.relative_to(PKG)
        assert "bedrock" not in src.lower(), (rel, "no direct AI integration — bring your own agent")
        if rel.parts[0] in ("pages", "components") or rel.name == "app.py":
            for sym in UI_SYMBOLS:
                assert sym not in src, (rel, sym)


if __name__ == "__main__":
    test_no_enterprise_modules_shipped_or_imported()
    test_no_enterprise_data_surfaces()
    test_no_enterprise_ui_or_ai_calls()
    print("ok")
