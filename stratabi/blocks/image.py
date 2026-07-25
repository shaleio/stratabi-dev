"""Image block — renders an image from a URL or a runtime artifact result."""
from dash import html
from stratabi.core.base import Block


class ImageBlock(Block):
    block_type = "image"

    def render(self):
        src = self.config.get("src")

        if isinstance(self.result, dict):
            src = (
                self.result.get("data_uri")
                or self.result.get("src")
                or self.result.get("url")
                or src
            )
        elif isinstance(self.result, str):
            src = self.result

        if not src:
            raise ValueError("Image block missing src.")
        
        return html.Img(
            src=src,
            alt=self.config.get("alt", ""),
            style={
                "width": self.config.get("width", "100%"),
                **self.config.get("style", {}),
            },
        )