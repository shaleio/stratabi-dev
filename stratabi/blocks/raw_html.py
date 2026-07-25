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
        
        return html.Iframe(
            srcDoc=content,
            style={
                "width": "100%",
                "height": self.config.get("height", "500px"),
                "border": "0",
                **self.config.get("style", {}),
            },
        )

