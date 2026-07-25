def render_dashboard(dashboard_json, visual_registry, theme):
    layout_components = []

    for block in dashboard_json["layout"]:
        vtype = block["type"]

        if vtype not in visual_registry:
            raise ValueError(f"Unknown visual type: {vtype}")

        renderer = visual_registry[vtype]
        component = renderer(
            query=block["query"],
            options=block.get("options", {}),
            theme=theme,
            position=block.get("position", {})
        )

        layout_components.append(component)

    return layout_components
