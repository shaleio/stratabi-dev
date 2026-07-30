'''
home.py — StrataBI Developer Edition splash / landing page (route "/").

A lightweight welcome screen that orients a developer: what this edition is and
the two things to do from here — author dashboards in the Builder and run them on
the Dashboard. Registered at the root path, so the navbar logo links back here.

Dev Edition only: this page is intentionally simple and has no admin/AI/RBAC
surface (those are hosted-Enterprise concerns).
'''

import os

import dash
from dash import html, dcc, register_page
import dash_bootstrap_components as dbc

try:
    from stratabi import __version__ as _VERSION
except Exception:  # pragma: no cover
    _VERSION = ""

register_page(__name__, path="/", name="Home")

# Guildmaster theme tokens (kept local so the splash renders on-theme without
# depending on any callback/registry).
_ACCENT = "#34b6c4"                       # teal fire
_TEXT_DIM = "rgba(230, 238, 245, 0.75)"   # frost white, dimmed
_PANEL = "rgba(255, 255, 255, 0.04)"
_BORDER = "1px solid rgba(52, 182, 196, 0.25)"


def _nav_card(title: str, body: str, href: str, cta: str):
    """A large clickable card that routes to one of the two working pages."""
    return dbc.Col(
        dcc.Link(
            dbc.Card(
                dbc.CardBody([
                    html.H4(title, className="mb-2", style={"color": "#ffffff"}),
                    html.P(body, className="mb-3", style={"color": _TEXT_DIM}),
                    html.Span(f"{cta}  →", style={"color": _ACCENT, "fontWeight": 600}),
                ]),
                className="h-100 shadow-sm",
                style={"background": _PANEL, "border": _BORDER, "borderRadius": "14px"},
            ),
            href=href,
            style={"textDecoration": "none"},
        ),
        md=6,
        className="mb-3",
    )


def layout():
    # Resolved live from the environment the app booted with (configure-local / .env).
    bucket = os.getenv("STRATABI_SYSTEM_BUCKET") or "(not configured)"
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "(unset)"

    return dbc.Container(
        [
            # Hero
            html.Div(
                [
                    html.Div(
                        "StrataBI · Developer Edition",
                        style={
                            "color": _ACCENT,
                            "letterSpacing": "0.15em",
                            "fontSize": "0.8rem",
                            "textTransform": "uppercase",
                            "marginBottom": "0.5rem",
                        },
                    ),
                    html.H1(
                        "Build and run dashboards on your own AWS data plane",
                        style={"color": "#ffffff", "fontWeight": 700, "maxWidth": "760px"},
                    ),
                    html.P(
                        "This is the local Developer Edition — a plain Python process on "
                        "your machine wired to Athena, Lambda, S3 and DynamoDB in your own "
                        "AWS account. Author declarative dashboard JSON in the Builder, "
                        "then execute and view it on the Dashboard.",
                        style={"color": _TEXT_DIM, "maxWidth": "720px", "fontSize": "1.05rem"},
                    ),
                ],
                className="py-4",
            ),

            # The two working destinations
            dbc.Row(
                [
                    _nav_card(
                        "Builder",
                        "Author and preview declarative dashboards — tiles, blocks, inputs "
                        "and query sources — and save them to your system bucket.",
                        "/builder",
                        "Open the Builder",
                    ),
                    _nav_card(
                        "Dashboard",
                        "Run a saved dashboard: tiles execute against Athena and your Lambda "
                        "modules and render live, with async status and downloadable artifacts.",
                        "/dashboard",
                        "Open a Dashboard",
                    ),
                ],
            ),

            # Connected data plane footer
            html.Div(
                [
                    html.Span("Connected data plane: ", style={"color": "rgba(230,238,245,0.55)"}),
                    html.Code(bucket, style={"color": _ACCENT, "background": "transparent"}),
                    html.Span("  ·  region ", style={"color": "rgba(230,238,245,0.55)"}),
                    html.Code(region, style={"color": _ACCENT, "background": "transparent"}),
                ],
                className="py-3",
                style={
                    "fontSize": "0.85rem",
                    "borderTop": "1px solid rgba(255,255,255,0.06)",
                    "marginTop": "1rem",
                },
            ),
            html.Div(
                f"\U0001F412\U0001F528  StrataBI Developer Edition"
                + (f" · v{_VERSION}" if _VERSION else ""),
                style={"color": "rgba(230,238,245,0.35)", "fontSize": "0.8rem"},
            ),
        ],
        fluid=False,
        className="py-4",
        style={"maxWidth": "980px"},
    )
