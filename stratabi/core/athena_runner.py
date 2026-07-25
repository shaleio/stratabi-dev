import os
import time
import boto3
import pandas as pd
import random
from botocore.exceptions import ClientError

from stratabi.core.config import config

WORKGROUPS = config.WORKGROUPS

def pick_workgroup():
    if not WORKGROUPS:
        return 'primary'
    return random.choice(WORKGROUPS)

class AthenaRunner:
    def __init__(self):
        self.region = os.getenv("AWS_REGION", "us-east-1")
        self.output = os.getenv("STRATABI_ATHENA_OUTPUT")
        self.workgroup = pick_workgroup()

        if not self.output:
            raise ValueError("Athena config missing: STRATABI_ATHENA_OUTPUT")

        self.client = boto3.client("athena", region_name=self.region)

    # -------------------------------------------------------
    # Run Query (Blocking Poll)
    # -------------------------------------------------------
    def run_query(self, query: str, database: str, timeout: int = 30):
        """Executes a SQL query and returns a pandas DataFrame."""
        if not database:
            raise ValueError("Database must be provided per query")

        try:
            response = self.client.start_query_execution(
                QueryString=query,
                QueryExecutionContext={"Database": database},
                ResultConfiguration={"OutputLocation": self.output},
                WorkGroup=self.workgroup
            )
        except ClientError as e:
            raise RuntimeError(f"Athena query failed to start: {e}")

        execution_id = response["QueryExecutionId"]
        return self._wait_for_results(execution_id, timeout)

    # -------------------------------------------------------
    # Wait for Athena completion
    # -------------------------------------------------------
    def _wait_for_results(self, execution_id: str, timeout: int):
        start_time = time.time()

        while True:
            result = self.client.get_query_execution(QueryExecutionId=execution_id)
            status = result["QueryExecution"]["Status"]["State"]

            if status == "SUCCEEDED":
                return self._fetch_results(execution_id)

            if status in ("FAILED", "CANCELLED"):
                reason = result["QueryExecution"]["Status"].get("StateChangeReason", "Unknown")
                raise RuntimeError(f"Athena query failed: {reason}")

            # timeout guard
            if (time.time() - start_time) > timeout:
                raise TimeoutError("Athena query timed out.")

            time.sleep(1)

    # -------------------------------------------------------
    # Fetch results into pandas
    # -------------------------------------------------------
    def _fetch_results(self, execution_id: str):
        paginator = self.client.get_paginator("get_query_results")
        pages = paginator.paginate(QueryExecutionId=execution_id)

        rows = []
        columns = []

        for i, page in enumerate(pages):
            rows_data = page["ResultSet"]["Rows"]

            # first page includes column metadata
            if i == 0:
                columns = [col["VarCharValue"] for col in rows_data[0]["Data"]]
                rows_data = rows_data[1:]

            for row in rows_data:
                rows.append([col.get("VarCharValue") for col in row["Data"]])

        df = pd.DataFrame(rows, columns=columns)
        return df
