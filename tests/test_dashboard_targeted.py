"""Regression tests for the dashboard.py targeted fixes (audit spec). Run with pytest or
`python tests/test_dashboard_targeted.py`."""
import os
import sys

sys.path[:0] = [os.path.dirname(__file__), os.path.dirname(os.path.dirname(__file__))]
import _stubs  # noqa: E402

_stubs.install()
import stratabi.pages.dashboard as d  # noqa: E402

NU = d.dash.no_update


# --- Run button targets only the clicked tile --------------------------------------------------
def test_run_button_ignores_mount_of_new_tile_after_another_was_clicked():
    _stubs.stub_ctx({"type": "tile-run", "tile_id": "B"}, value=0)  # B mounted, never clicked
    assert d.run_tile_button([3, 0], "u", "k") == NU          # A had 3 clicks earlier
    _stubs.stub_ctx({"type": "tile-run", "tile_id": "B"}, value=None)
    assert d.run_tile_button([3, None], "u", "k") == NU


def test_run_button_targets_clicked_tile():
    _stubs.stub_ctx({"type": "tile-run", "tile_id": "B"}, value=1)
    out = d.run_tile_button([3, 1], "u", "k")
    assert out["target_tile_id"] == "B"


# --- Interval / always tiles schedule their next run -------------------------------------------
def _async_tile(mode):
    return {"id": "t", "exec": {"type": "lambda", "module_id": "m", "lambda_index": 0},
            "load": {"mode": mode}}


def test_interval_async_tile_runs_again_after_success():
    for mode in ("interval", "always"):
        assert d.should_execute_tile(_async_tile(mode), "dashboard-interval", tile_status="SUCCEEDED")
        assert d.should_execute_tile(_async_tile(mode), "dashboard-interval", tile_status="FAILED")


def test_interval_does_not_rerun_load_once_or_duplicate_active():
    assert not d.should_execute_tile(_async_tile("load_once"), "dashboard-interval", tile_status="SUCCEEDED")
    assert not d.should_execute_tile(_async_tile("interval"), "dashboard-interval", tile_status="RUNNING")
    assert d.should_check_tile(_async_tile("interval"), "dashboard-interval", "RUNNING")
    sync = {"id": "s", "exec": {"type": "athena"}, "load": {"mode": "interval"}}
    assert d.should_execute_tile(sync, "dashboard-interval", tile_status=None)


# --- App Refresh never runs action (manual) tiles ----------------------------------------------
def test_app_refresh_requeries_views_but_not_actions():
    view = {"id": "v", "exec": {"type": "lambda", "sync": True}, "load": {"mode": "load_once"}}
    action = {"id": "a", "exec": {"type": "lambda", "sync": True}, "load": {"mode": "manual"}}
    assert d.should_execute_tile(view, "dashboard-refresh-store", app_route=True)
    assert not d.should_execute_tile(action, "dashboard-refresh-store", app_route=True)
    # ordinary dashboards keep their existing refresh semantics
    assert d.should_execute_tile(action, "dashboard-refresh-store", app_route=False)


# --- Input defaults --------------------------------------------------------------------------
def test_input_defaults_cover_all_input_blocks_and_validate_static_options():
    cfg = {"layout": [
        {"id": "a", "block": {"type": "input_select", "config": {"input_id": "region", "default": "us",
                                                                "options": ["us", "eu"]}}},
        {"id": "b", "block": {"type": "dropdown", "config": {"input_id": "dd", "value": "x",
                                                            "options": [{"label": "X", "value": "x"}]}}},
        {"id": "c", "block": {"type": "input_text", "config": {"input_id": "q", "default": "hi"}}},
        {"id": "e", "block": {"type": "input_range", "config": {"input_id": "n", "value": 5}}},
        {"id": "f", "block": {"type": "input_select", "config": {"input_id": "bad", "default": "zz",
                                                                "options": ["us"]}}},
    ]}
    assert d._input_defaults_from_config(cfg) == {"region": "us", "dd": "x", "q": "hi", "n": 5}


def test_url_values_only_for_declared_inputs():
    cfg = {"layout": [{"id": "a", "block": {"type": "input_select", "config": {
        "input_id": "region", "options": ["us", "eu"]}}}]}
    assert d._url_input_values(cfg, "?region=eu&other=1") == {"region": "eu"}


# --- Single-page modules resolve ?source; module UI flags ------------------------------------
def test_module_ui_flags_default_off():
    assert d._module_ui({}) == {"show_refresh": False, "show_status": False, "card_style": None}
    assert d._module_ui({"ui": {"show_refresh": True}})["show_refresh"] is True


def test_single_page_module_resolves_sources(monkeypatch=None):
    calls = []
    orig = d.resolve_sources_in_config
    d.resolve_sources_in_config = lambda c: calls.append(c) or c
    try:
        old = d.load_module_json
        d.load_module_json = lambda mid: {"module_id": "solo", "module_type": "single_page_app",
                                          "layout": [{"id": "x"}], "label": "Solo"}
        _stubs.stub_ctx("module-active-page-store")
        cfg, _ = d.load_dashboard_config("/dashboard/apps/solo", None, None, "", None, "u", {}, {})
        assert calls and cfg["id"] == "solo" and "_module_ui" in cfg
    finally:
        d.resolve_sources_in_config = orig
        d.load_module_json = old


# --- Selector discovery skipped on app routes --------------------------------------------------
def test_selector_not_populated_on_app_routes():
    called = []
    orig = d.list_dashboard_options
    d.list_dashboard_options = lambda **k: called.append(1) or []
    try:
        assert d.populate_dashboard_selector(None, "u", None, None, "/dashboard/apps/stratamail", "", None) == (NU, NU)
        assert not called
        d.populate_dashboard_selector(None, "u", None, None, "/dashboard", "", None)
        assert called
    finally:
        d.list_dashboard_options = orig


# --- Toolbar on app routes ---------------------------------------------------------------------
def test_toolbar_hidden_for_apps_unless_opted_in():
    hide = {"display": "none"}
    assert d.toggle_dashboard_controls("/dashboard/apps/m", {"_module_ui": {}})[0] is True
    out = d.toggle_dashboard_controls("/dashboard/apps/m", {"_module_ui": {"show_refresh": True, "show_status": True}})
    assert out[0] is False and out[1] == hide and out[2] == {} and out[3] == {}
    assert len(out) == 4  # selector, refresh, status — no favorite/git controls in this edition
    assert d.toggle_dashboard_controls("/dashboard", None)[0] is False


def test_refresh_reload_only_for_dashboard_source_pages():
    _stubs.stub_ctx("dashboard-refresh-store")
    try:
        d.load_dashboard_config("/dashboard", "k", None, "", {"ts": 1}, "u", {}, {})
        raise AssertionError("expected PreventUpdate")
    except _stubs.PreventUpdate:
        pass




# --- app card styles (module.json ui.card_style) ------------------------------------------------
def test_card_style_match_uses_module_html_background_and_bares_text_tiles():
    import os
    os.environ["STRATABI_THEME"] = "darkly"
    layout = [
        {"id": "intro", "block": {"type": "markdown", "config": {"content": "## Hi"}}},
        {"id": "view", "title": "View", "exec": {"type": "lambda"}, "block": {"type": "raw_html", "config": {"html": ""}}},
        {"id": "own", "card": {"color": "danger"}, "exec": {"type": "lambda"}, "block": {"type": "table", "config": {}}},
    ]
    out = d._apply_card_style(layout, "match")
    assert out[0]["_card_class"] == "sbi-card-bare"
    assert out[1]["_card_class"] == "sbi-card-match sbi-surface-dark" and out[1]["card"]["outline"] is False
    assert out[2]["card"] == {"color": "danger"} and "_card_class" not in out[2]   # own color wins
    assert "card" not in layout[1]                                # module JSON untouched
    os.environ["STRATABI_THEME"] = "flatly"
    assert d._apply_card_style(layout, "match")[1]["_card_class"].endswith("sbi-surface-light")
    css = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "stratabi", "assets", "module-cards.css")).read()
    assert "#0d1117 !important" in css and "#ffffff !important" in css


def test_card_style_muted_and_off():
    layout = [{"id": "v", "exec": {"type": "lambda"}, "block": {"type": "table", "config": {}}}]
    assert d._apply_card_style(layout, "muted")[0]["card"] == {"color": "secondary", "outline": True}
    assert d._apply_card_style(layout, None) is layout
    assert d._module_ui({"ui": {"card_style": "neon"}})["card_style"] is None


# --- JSON results are data, not run statuses -----------------------------------------------------
def test_json_option_payload_is_not_read_as_running():
    assert d._run_status({"options": [{"label": "a", "value": "a"}]}) is None      # dropdown feed
    assert d._run_status({"value": "Weekly"}) is None                              # input_text prefill
    assert d._run_status({"status": "ok", "rows": 3}) is None                      # payload's own field
    assert d._run_status({"status": "RUNNING"}) == "RUNNING"
    assert d._run_status({"status": "failed", "message": "x"}) == "FAILED"
    assert d._run_status({"status": "succeeded", "result_s3_key": "k"}) == "SUCCEEDED"
    assert d._run_status("<p>html</p>") is None


def test_executing_tiles_reserve_their_height():
    lam = {"type": "lambda"}
    assert d._reserved_height({"exec": lam, "block": {"type": "raw_html", "config": {"height": "560px"}}}) == "560px"
    assert d._reserved_height({"exec": lam, "block": {"type": "table", "config": {}}}) == "500px"
    assert d._reserved_height({"exec": lam, "block": {"type": "plotly", "config": {
        "figure": {"layout": {"height": 280}}}}}) == "280px"
    assert d._reserved_height({"exec": lam, "block": {"type": "input_select", "config": {}}}) == "38px"
    assert d._reserved_height({"exec": lam, "block": {"type": "markdown", "config": {}}}) is None
    assert d._reserved_height({"block": {"type": "table", "config": {}}}) is None   # static: no reservation


# --- keep_previous: last successful result stays visible while a new run is in flight -----------
def _keep_cfg(keep=True):
    tile = {"id": "conv", "exec": {"type": "lambda", "module_id": "m", "lambda_index": 0},
            "load": {"mode": "input", "keep_previous": keep},
            "block": {"type": "raw_html", "config": {"html": "", "height": "300px"}}}
    return {"_dashboard_key": "k", "layout": [tile]}


def _run_update(cfg, trigger, exec_result, prev=None, status_store=None):
    orig_exec, orig_prev = d.execute_tile, d._last_success_result
    d.execute_tile = lambda *a, **k: exec_result
    d._last_success_result = lambda *a, **k: prev
    _stubs.stub_ctx(trigger, 1)
    try:
        return d.update_tile(cfg, None, 1, None, None, {}, "k", {"runtime_session_id": "rs"},
                             status_store, {"tile_id": "conv"}, "")
    finally:
        d.execute_tile, d._last_success_result = orig_exec, orig_prev


def test_keep_previous_leaves_content_and_shows_updating():
    out = _run_update(_keep_cfg(), "dashboard-trigger-store", {"status": "RUNNING"}, status_store="SUCCEEDED")
    assert out[0] == d.dash.no_update and out[1] == "RUNNING" and "sbi-building-badge" in out[2].kw["className"]


def test_keep_previous_failure_marks_stale_and_keeps_content():
    out = _run_update(_keep_cfg(), "dashboard-interval", {"status": "FAILED", "message": "module timed out"},
                      status_store="RUNNING")
    assert out[0] == d.dash.no_update and out[1] == "FAILED"
    assert "stale" in out[2].children and "module timed out" in out[2].children


def test_keep_previous_on_mount_renders_last_success_with_badge():
    out = _run_update(_keep_cfg(), None, {"status": "RUNNING"}, prev="<p>old transcript</p>")
    assert out[1] == "RUNNING" and "sbi-building-badge" in out[2].kw["className"]
    assert out[0].kw.get("srcDoc") == "<p>old transcript</p>"


def test_without_keep_previous_processing_replaces_content():
    out = _run_update(_keep_cfg(False), "dashboard-trigger-store", {"status": "RUNNING"})
    assert out[1] == "RUNNING" and "sbi-building" == out[0].kw["className"]


def test_stacked_tiles_share_one_column_beside_others():
    def t(i, order, width, stack=None):
        pos = {"row": 1, "order": order, "width": width}
        if stack:
            pos["stack"] = stack
        return {"id": i, "position": pos, "block": {"type": "markdown", "config": {"content": i}}}
    cfg = {"_dashboard_key": "k", "layout": [t("session", 0, 3, "controls"), t("conv", 1, 9, "chat"),
                                            t("model", 2, 3, "controls"), t("prompt", 3, 9, "chat")]}
    rows = d.build_dashboard_grid(cfg)
    cols = rows[0].children
    assert len(cols) == 2 and cols[0].kw["md"] == 3 and cols[1].kw["md"] == 9
    left = [c.children for c in cols[0].children]                  # cards in the left column
    assert len(cols[0].children) == 2 and "h-100" not in cols[0].children[0].kw["className"]


def test_inputs_survive_tab_switches_within_one_app_only():
    ids = [{"type": "tile-input", "tile_id": "session_id"}]
    first, _ = d.store_inputs(["s-123"], ids, "u", None, None, "/dashboard/apps/stratachat")
    # Workspace tab: no inputs mounted -> the chosen session is kept
    ws, _ = d.store_inputs([], [], "u", None, first, "/dashboard/apps/stratachat")
    assert ws["inputs"]["session_id"] == "s-123"
    # another app/dashboard: nothing carried over
    other, _ = d.store_inputs([], [], "u", None, first, "/dashboard/apps/stratamail")
    assert other["inputs"] == {}


def test_triggered_by_accepts_input_tile_ids_or_input_ids():
    config = {"layout": [
        {"id": "region_input", "block": {"type": "input_select", "config": {"input_id": "region"}}},
        {"id": "by_tile", "triggered_by": ["region_input"], "load": {"mode": "input"}, "exec": {"type": "athena"}},
        {"id": "by_input", "triggered_by": ["region"], "load": {"mode": "input"}, "exec": {"type": "athena"}},
        {"id": "other", "triggered_by": ["nope"], "load": {"mode": "input"}, "exec": {"type": "athena"}},
    ]}
    bus = {"trigger_tile_id": "region"}   # input components are keyed by input_id
    for tid, expected in (("by_tile", True), ("by_input", True), ("other", False)):
        tile = d._with_resolved_triggers(d.get_tile_by_id(config, tid), config)
        assert d.should_execute_tile(tile, "dashboard-trigger-store", bus) is expected, tid


def test_slider_feeds_the_input_store_and_shows_its_value():
    from stratabi.blocks.input_range import InputRangeBlock
    blk = InputRangeBlock.__new__(InputRangeBlock)
    blk.config = {"input_id": "duration_minutes", "label": "Session", "min": 30, "max": 480, "value": 240}
    comp = blk.render()
    kw = getattr(comp, "kw", None) or comp.__dict__
    assert kw["id"] == {"type": "tile-input", "tile_id": "duration_minutes"}
    assert kw["value"] == 240 and kw["tooltip"]["always_visible"] is True


def test_building_indicator_is_a_badge_plus_quiet_hint():
    ind = d.building_indicator({"id": "t1"}, now=1000.0)
    badge, hint = ind.children
    assert badge.children.rstrip("…") in d.BUILDING_WORDS and "badge" in badge.kw["className"]
    assert hint.children == "Refresh to check"
    # stable within a period (no flicker on re-render), moves on later; every worker agrees (crc32)
    assert d.building_word("t1", 1000.0) == d.building_word("t1", 1000.0 + d._WORD_PERIOD_S - 1 - 1000.0 % d._WORD_PERIOD_S)
    assert d.building_word("t1", 1000.0).endswith("…")
    assert len(set(d.BUILDING_WORDS)) == len(d.BUILDING_WORDS)
    # non-manual exec tile without its own placeholder gets the indicator; manual keeps its prompt
    assert d._initial_tile_content({"id": "t", "exec": {"type": "athena"}}, None, None).kw["className"] == "sbi-building"
    manual = d._initial_tile_content({"id": "t", "exec": {"type": "athena"}, "load": {"mode": "manual"}}, None, None)
    assert "▷" in manual.children


def test_tile_flavor_text_overrides_the_bank():
    one = d.building_indicator({"id": "t", "flavor_text": "Logging"}, now=5.0)
    assert one.children[0].children == "Logging…"
    rot = {d.building_word({"id": "t", "flavor_text": ["Coring", "Logging..."]}, now=n * d._WORD_PERIOD_S)
           for n in range(40)}
    assert rot <= {"Coring…", "Logging..."} and len(rot) == 2
    # blank / wrong types fall back to the default bank
    for bad in ("", [], ["  "], 7, None):
        assert d.building_word({"id": "t", "flavor_text": bad}, now=5.0).rstrip("…") in d.BUILDING_WORDS
    # keep_previous badge uses it too
    assert d._badge("RUNNING", None, {"id": "t", "flavor_text": "Logging"}).children == "Logging…"



def test_action_completion_reruns_only_tiles_that_name_it():
    cfg = {"layout": [
        {"id": "run", "load": {"mode": "manual"}, "exec": {"type": "lambda", "sync": True}},
        {"id": "list", "triggered_by": ["run"], "load": {"mode": "load_once"}, "exec": {"type": "lambda", "sync": True}},
        {"id": "loose", "load": {"mode": "input"}, "exec": {"type": "lambda", "sync": True}},
    ]}
    run = {"target_tile_id": "run"}
    assert d._action_done(cfg, "run", "dashboard-run-store", run, None, "content", NU) is not NU
    assert d._action_done(cfg, "run", "dashboard-run-store", run, None, "err", "FAILED") is NU
    assert d._action_done(cfg, "list", "dashboard-run-store", {"target_tile_id": "list"}, None, "x", NU) is NU  # nobody names it
    # async action: done when polling first sees success
    assert d._action_done(cfg, "run", "dashboard-interval", None, "RUNNING", "c", "SUCCEEDED") is not NU
    assert d._action_done(cfg, "run", "dashboard-interval", None, "SUCCEEDED", "c", "SUCCEEDED") is NU
    bus = {"trigger_type": "action", "trigger_tile_id": "run"}
    tiles = {t["id"]: t for t in cfg["layout"]}
    assert d.should_execute_tile(tiles["list"], "dashboard-trigger-store", bus, tile_status="SUCCEEDED") is True
    assert d.should_execute_tile(tiles["loose"], "dashboard-trigger-store", bus) is False   # input-mode tiles ignore actions
    assert d.should_execute_tile(tiles["run"], "dashboard-trigger-store", bus) is False


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
