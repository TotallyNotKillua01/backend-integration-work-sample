import os
from pathlib import Path

from fastapi.testclient import TestClient

import app as sample_app


def setup_module():
    if sample_app.DB_PATH.exists():
        os.remove(sample_app.DB_PATH)
    sample_app.init_db()


client = TestClient(sample_app.app)


def test_end_to_end_flow():
    customer = client.post(
        "/customers",
        json={"email": "sample@example.com", "full_name": "Sample User"},
    )
    assert customer.status_code == 201
    customer_id = customer.json()["id"]

    kit = client.post(
        "/kits/register",
        json={"kit_code": "KIT-AB12CD34", "customer_id": customer_id},
    )
    assert kit.status_code == 201
    kit_id = kit.json()["id"]

    job = client.post(
        "/processing-jobs",
        json={"kit_id": kit_id, "pipeline_version": "v1"},
    )
    assert job.status_code == 201
    job_id = job.json()["id"]

    finished = client.patch(
        f"/processing-jobs/{job_id}", json={"status": "succeeded"}
    )
    assert finished.status_code == 200

    report = client.post(
        "/reports",
        json={
            "kit_id": kit_id,
            "report_version": "v1",
            "summary": "Synthetic wellness report generated for portfolio demonstration only.",
        },
    )
    assert report.status_code == 201

    dashboard = client.get(f"/customers/{customer_id}/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["kits"][0]["report_id"] is not None
