"""Module Lambda payload: actor stamping and ephemeral (inline_html) sync results."""
import os
import sys
from unittest.mock import MagicMock

sys.path[:0] = [os.path.dirname(__file__), os.path.dirname(os.path.dirname(__file__))]
import _stubs  # noqa: E402

_stubs.install()
import stratabi.core.runner as r  # noqa: E402

TILE = {"id": "open", "exec": {"type": "lambda", "module_id": "nb", "lambda_index": 0, "sync": True},
        "block": {"type": "raw_html", "config": {}}}


def _patch(body):
    r.resolve_module_for_execution = lambda mid, idx: {"module_id": mid, "lambda_index": idx,
                                                       "lambda_arn": "arn:x"}
    seen = {}

    def fake_invoke(arn, payload, timeout):
        seen["payload"] = payload
        return {"payload": body, "function_error": None}
    r.invoke_lambda_sync = fake_invoke
    table = MagicMock()
    r._get_status_table = lambda: table
    return seen, table


def test_actor_is_the_unverified_shared_actor():
    # The Developer Edition has no sign-in: modules see exactly what a deployment without auth sends.
    seen, _ = _patch({"inline_html": "<p>x</p>"})
    r._run_lambda_sync(TILE, TILE["exec"], {}, "k", "rs1")
    sc = seen["payload"]["status_context"]
    assert (sc["actor"], sc["actor_verified"], sc["auth_mode"]) == ("anonymous", False, "none")


def test_inline_html_is_returned_and_never_recorded():
    _, table = _patch({"status": "SUCCEEDED", "inline_html": "<a href='https://secret'>open</a>"})
    out = r._run_lambda_sync(TILE, TILE["exec"], {}, "k", "rs1")
    assert out == "<a href='https://secret'>open</a>"
    table.put_item.assert_not_called()


def test_failed_inline_still_fails():
    _patch({"status": "FAILED", "message": "nope", "inline_html": "x"})
    out = r._run_lambda_sync(TILE, TILE["exec"], {}, "k", "rs1")
    assert out["status"] == "FAILED"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
