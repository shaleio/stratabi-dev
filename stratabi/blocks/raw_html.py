"""Raw-HTML block — renders trusted HTML content (gated; use with care)."""
from dash import html
from stratabi.core.base import Block
from stratabi.core.text_utils import coerce_lines


class RawHTMLBlock(Block):
    block_type = "raw_html"

    def render(self):
        content = coerce_lines(self.config.get("html", ""))

        if isinstance(self.result, str):
            content = self.result
        elif isinstance(self.result, dict):
            content = (
                self.result.get("html")
                or self.result.get("content")
                or content
            )

        if not content:
            raise ValueError("Raw HTML block missing html content.")

        # Sandbox the iframe so embedded scripts can't reach the parent app's origin
        # (cookies, localStorage, same-origin APIs). Default deliberately OMITS
        # allow-same-origin: scripts still run (charts, viz), but in a null origin, so a
        # malicious/compromised raw_html can't hijack the session. Override per block via
        # `sandbox` (set it to null to opt out entirely for a fully trusted embed).
        iframe_kwargs = {
            "srcDoc": content,
            "style": {
                "width": "100%",
                "height": self.config.get("height", "500px"),
                "border": "0",
                **self.config.get("style", {}),
            },
        }
        sandbox = self.config.get("sandbox", "allow-scripts allow-popups")
        if sandbox is not None:
            iframe_kwargs["sandbox"] = sandbox

        return html.Iframe(**iframe_kwargs)

