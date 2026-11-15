"""Session dashboards (dashboard_source) are read from the system bucket."""
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.dirname(__file__), ROOT]
import _stubs  # noqa: E402

_stubs.install()


def test_reads_from_the_system_bucket():
    os.environ["STRATABI_SYSTEM_BUCKET"] = "sys-bucket"
    os.environ.pop("STRATABI_BUCKET", None)
    from stratabi.core import loader
    loader.config.MODE = "aws"
    seen = {}

    class S3:
        def get_object(self, Bucket, Key):
            seen["bucket"], seen["key"] = Bucket, Key
            return {"Body": io.BytesIO(json.dumps({"layout": [{"id": "a"}]}).encode())}

    import boto3
    boto3.client = lambda *a, **k: S3()
    doc = loader.load_dashboard_by_s3_key("stratachat/rt/rs1/s1/current.json")
    assert seen == {"bucket": "sys-bucket", "key": "stratachat/rt/rs1/s1/current.json"}
    assert doc["layout"][0]["id"] == "a"


if __name__ == "__main__":
    test_reads_from_the_system_bucket()
    print("ok")
