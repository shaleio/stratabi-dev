'''
navbar.py

Provides a framework for a logo, title, web page nav links, and dropdowns
'''

'''Imports'''
import dash
from dash import html, dcc
import dash_bootstrap_components as dbc
import base64

'''define logo'''
def encode_logo(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

logo_b64 = encode_logo("stratabi/assets/logo.png")


'''define navbar'''

navbar = dbc.Navbar(
    dbc.Container(
        fluid=True,
        children=[
            # LEFT SIDE — Logo + Left Nav
            dbc.Row(
                align="center",
                className="g-0",
                children=[
                    # --- LOGO BADGE (Option 1) ---
                    dbc.Col(
                        html.Div(
                            html.Img(
                                src=f"data:image/png;base64,{logo_b64}",
                                height="38px",
                                style={
                                    "objectFit": "contain",
                                    "zIndex": 10,
                                },
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
                        width="auto",
                    ),

                    # LEFT NAV LINKS
                    dbc.Col(
                        dbc.Nav(
                            [
                                dbc.NavLink("Builder", href="/", active="exact"),
                                dbc.NavLink("Dashboard", href="/dashboard", active="exact"),
                            ],
                            className="me-auto",
                            navbar=True,
                        ),
                        width="auto",
                    ),
                ],
            ),

            # RIGHT NAV
            dbc.Nav(
                [
                    dbc.NavLink(
                        "Docs",
                        href="https://shaleio.com",
                        target="_blank",
                        external_link=True,
                    ),
                ],
                className="ms-auto",
                navbar=True,
            ),
            dbc.Button(
                "Apps",
                id="navbar-apps-button",
                color="info",
                outline=True,
                n_clicks=0,
            )
        ],
    ),
    color="#0a0d14",
    dark=True,
    sticky="top",
    style={"height": "60px"},
)
