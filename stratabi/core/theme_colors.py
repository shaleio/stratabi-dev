"""Theme-aware Plotly colors.

Every app theme ships with the package (stratabi/themes/*.css) and declares its palette as Bootstrap
CSS variables (--bs-primary, --bs-body-color, --bs-border-color, ...). This reads the active theme's
values once per process and turns them into Plotly layout defaults, so charts match the page:

  colorway   primary, info, success, warning, danger (series colors, in that order)
  text       body color + the theme's font family
  gridlines  the border color, faded
  hover      theme background + text

Opt-in per chart with plotly / plotly_resampler `config.theme_colors: true` (dashboard schema 1.5.0),
or deployment-wide with STRATABI_PLOTLY_THEME_COLORS=1. Explicit figure values always win: these are
only defaults, merged under whatever the figure already sets.
"""
from __future__ import annotations

import functools
import logging
import os
import re
from importlib.resources import files

logger = logging.getLogger(__name__)

_VAR = re.compile(r"--bs-([a-z0-9-]+)\s*:\s*([^;}]+)")
_WANTED = ("primary", "secondary", "success", "info", "warning", "danger", "body-color", "body-bg",
           "border-color", "body-font-family", "font-sans-serif", "emphasis-color", "secondary-color")


def active_theme() -> str:
    return os.getenv("STRATABI_THEME", "guildmaster").strip().lower()


def _theme_css(name: str) -> str | None:
    try:
        root = files("stratabi").joinpath("themes")
        for candidate in (f"{name}.css", f"{name}.min.css"):
            f = root.joinpath(candidate)
            if f.is_file():
                return f.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.info("theme css for %s unavailable: %s", name, exc)
    return None


def _resolve(value: str, vars_: dict, depth: int = 0) -> str:
    value = value.strip().replace("!important", "").strip()
    m = re.fullmatch(r"var\(--bs-([a-z0-9-]+)(?:\s*,\s*(.+))?\)", value)
    if m and depth < 5:
        ref = vars_.get(m.group(1))
        return _resolve(ref, vars_, depth + 1) if ref else (m.group(2) or "").strip()
    return value


def palette(name: str | None = None) -> dict | None:
    """The theme's colors (first declaration of each --bs-* variable = the theme's base :root),
    or None when the theme isn't bundled (custom themes fall back to the plain template)."""
    return _palette(name or active_theme())


@functools.lru_cache(maxsize=32)
def _palette(name: str) -> dict | None:
    css = _theme_css(name)
    if not css:
        return None
    vars_: dict = {}
    for key, val in _VAR.findall(css):
        vars_.setdefault(key, val)
    out = {k: _resolve(vars_[k], vars_) for k in _WANTED if k in vars_}
    return out if out.get("primary") else None


def _rgba(color: str, alpha: float) -> str:
    c = (color or "").strip()
    m = re.fullmatch(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", c)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        return f"rgba({r},{g},{b},{alpha})"
    m = re.fullmatch(r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*,\s*[\d.]+)?\s*\)", c)
    if m:
        return f"rgba({m.group(1)},{m.group(2)},{m.group(3)},{alpha})"
    return c or f"rgba(127,127,127,{alpha})"


def layout_defaults(name: str | None = None) -> dict | None:
    """Plotly layout defaults for the theme (None if unknown)."""
    p = palette(name)
    if not p:
        return None
    text = p.get("body-color") or p.get("emphasis-color")
    grid = _rgba(p.get("border-color") or text or "#7f7f7f", 0.25)
    font = {k: v for k, v in (("color", text), ("family", p.get("body-font-family") or p.get("font-sans-serif")))
            if v}
    axis = {"gridcolor": grid, "linecolor": grid, "zerolinecolor": grid,
            "tickfont": {"color": text} if text else {}, "title": {"font": {"color": text}} if text else {}}
    # secondary is often a near-background tone in dark themes: not a usable series color
    colorway = [p[k] for k in ("primary", "info", "success", "warning", "danger") if p.get(k)]
    out = {"colorway": colorway, "font": font, "xaxis": axis, "yaxis": dict(axis),
           "legend": {"font": {"color": text}} if text else {},
           "title": {"font": {"color": text}} if text else {}}
    if p.get("body-bg"):
        out["hoverlabel"] = {"bgcolor": p["body-bg"], "bordercolor": grid,
                             "font": {"color": text} if text else {}}
    return out


def _merge_defaults(target: dict, defaults: dict) -> dict:
    """Fill `defaults` into `target` without overwriting anything target already sets."""
    for k, v in defaults.items():
        if isinstance(v, dict):
            cur = target.get(k)
            if cur is None:
                target[k] = _merge_defaults({}, v)
            elif isinstance(cur, dict):
                _merge_defaults(cur, v)
            # a non-dict explicit value (e.g. title as a string) wins as-is
        elif k not in target:
            target[k] = v
    return target


def enabled(config: dict | None) -> bool:
    flag = (config or {}).get("theme_colors")
    if flag is not None:
        return bool(flag)
    return os.getenv("STRATABI_PLOTLY_THEME_COLORS", "").strip().lower() in ("1", "true", "yes", "on")


def apply(layout: dict, config: dict | None = None) -> dict:
    """Merge theme defaults into a figure layout (in place) when enabled for this block."""
    if not enabled(config):
        return layout
    d = layout_defaults()
    if d:
        # A string title ("Pressure") can't take nested font defaults; leave it alone.
        if isinstance(layout.get("title"), str):
            d = {k: v for k, v in d.items() if k != "title"}
        for ax in ("xaxis", "yaxis"):
            if isinstance((layout.get(ax) or {}).get("title"), str):
                d[ax] = {k: v for k, v in d[ax].items() if k != "title"}
        _merge_defaults(layout, d)
    return layout
