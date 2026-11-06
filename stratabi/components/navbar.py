'''
navbar.py

Provides a framework for a logo, title, web page nav links, and dropdowns
'''

'''Imports'''
import dash
from dash import html, dcc, callback, Input, Output, State
import dash_bootstrap_components as dbc
import base64
from pathlib import Path

# Assets live inside the installed package (stratabi/assets), so resolve them
# relative to this file — NOT the current working directory. A cwd-relative path
# breaks when the app is launched from anywhere but the repo root (e.g. after
# `pipx install stratabi`, where cwd is the user's home dir).
_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

'''define logo'''
def encode_logo(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

logo_b64 = encode_logo(_ASSETS_DIR / "logo.png")


'''define navbar'''

navbar = dbc.Navbar(
    dbc.Container(
        fluid=True,
        children=[
            # Brand (logo) — always visible, links home to the splash page.
            dcc.Link(
                html.Div(
                    html.Img(
                        src=f"data:image/png;base64,{logo_b64}",
                        height="38px",
                        style={"objectFit": "contain", "zIndex": 10},
                    ),
                    style={
                        "padding": "6px 10px",
                        "borderRadius": "12px",
                        "background": "rgba(255, 255, 255, 0.08)",
                        "backdropFilter": "blur(4px)",
                        "display": "flex",
                        "alignItems": "center",
                        "justifyContent": "center",
                    },
                ),
                href="/",
                className="navbar-brand p-0 me-2",
            ),

            # Hamburger toggler — shown below the `expand` breakpoint (md) only.
            dbc.NavbarToggler(id="navbar-toggler", n_clicks=0),

            # Collapsible nav — auto-expanded on >=md, toggled by the hamburger on
            # narrow/portrait viewports (e.g. an AI tool opening 127.0.0.1 in a
            # portrait browser window).
            dbc.Collapse(
                id="navbar-collapse",
                navbar=True,
                is_open=False,
                children=[
                    dbc.Nav(
                        [
                            dbc.NavLink("Builder", href="/builder", active="exact"),
                            dbc.NavLink("Dashboard", href="/dashboard", active="exact"),
                        ],
                        navbar=True,
                    ),
                    dbc.Nav(
                        [
                            dbc.NavLink(
                                "Docs",
                                href="https://shaleio.com",
                                target="_blank",
                                external_link=True,
                            ),
                        ],
                        navbar=True,
                        className="ms-auto",
                    ),
                    dbc.Button(
                        "Apps",
                        id="navbar-apps-button",
                        color="info",
                        outline=True,
                        n_clicks=0,
                        className="ms-md-2 mt-2 mt-md-0",
                    ),
                ],
            ),
        ],
    ),
    color="#0a0d14",
    dark=True,
    sticky="top",
    expand="md",
    style={"minHeight": "60px"},
)


# Toggle the collapsed nav on mobile (no-op on desktop, where it's always expanded).
@callback(
    Output("navbar-collapse", "is_open"),
    Input("navbar-toggler", "n_clicks"),
    State("navbar-collapse", "is_open"),
    prevent_initial_call=True,
)
def _toggle_navbar(_n, is_open):
    return not is_open
