from app.models import JobStatus
from app.schemas import JobCreate
from app import service

from tests.conftest import make_payload


def test_create_job_returns_accepted_with_links(submit):
    resp = submit([{"name": "Asha Rao"}, {"name": "Ravi Kumar"}, {"name": "Meena Iyer"}])
    assert resp.status_code == 202
    body = resp.json()
    assert body["total"] == 3
    assert body["links"]["self"] == f"/api/jobs/{body['id']}/"


def test_job_completes_in_background(client, submit):
    job_id = submit([{"name": "Asha Rao"}, {"name": "Ravi Kumar"}]).json()["id"]
    body = client.get(f"/api/jobs/{job_id}/").json()
    assert body["status"] == "COMPLETED"
    assert body["completed"] == 2 and body["failed"] == 0
    assert body["finished_at"] is not None


def test_new_job_is_pending_before_processing(client):
    # Call the service directly (no background task) to observe the initial state.
    with client.app.state.session_factory() as session:
        job = service.create_job(
            session, JobCreate(**make_payload([{"name": "Asha Rao"}, {"name": "Ravi"}]))
        )
        assert job.status == JobStatus.PENDING
        assert (job.total, job.completed, job.failed) == (2, 0, 0)


def test_issue_date_defaults_to_today(client, submit):
    payload = make_payload([{"name": "Asha"}])
    del payload["issue_date"]
    resp = client.post("/api/jobs/", json=payload)
    assert resp.status_code == 202
    assert resp.json()["issue_date"]
