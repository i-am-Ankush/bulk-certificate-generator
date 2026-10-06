from app import pdf
from app.models import Job


def test_unrenderable_name_fails_only_that_certificate(client, submit):
    resp = submit([{"name": "Asha Rao"}, {"name": "अंकुश कुमार"}, {"name": "Meena Iyer"}])
    body = client.get(f"/api/jobs/{resp.json()['id']}/").json()

    assert body["status"] == "COMPLETED_WITH_ERRORS"
    assert (body["completed"], body["failed"]) == (2, 1)
    assert body["failures"][0]["index"] == 2
    assert "cannot render" in body["failures"][0]["error"]


def test_exception_in_renderer_is_isolated(client, submit, monkeypatch, settings):
    real = pdf.render_certificate

    def flaky(path, data):
        if data.recipient_name == "Boom":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"partial")  # simulate a half-written file
            raise RuntimeError("disk exploded")
        return real(path, data)

    monkeypatch.setattr(pdf, "render_certificate", flaky)
    job_id = submit([{"name": "Asha"}, {"name": "Boom"}, {"name": "Ravi"}]).json()["id"]
    body = client.get(f"/api/jobs/{job_id}/").json()

    assert body["status"] == "COMPLETED_WITH_ERRORS"
    assert body["failures"] == [{"index": 2, "recipient_name": "Boom", "error": "disk exploded"}]
    # the half-written file was cleaned up, the good ones exist
    files = sorted(p.name for p in (settings.storage_dir / job_id).iterdir())
    assert len(files) == 2 and all(not f.startswith("00002") for f in files)


def test_every_certificate_failing_marks_job_failed(client, submit, monkeypatch):
    def always_fail(path, data):
        raise RuntimeError("nope")

    monkeypatch.setattr(pdf, "render_certificate", always_fail)
    job_id = submit([{"name": "A"}, {"name": "B"}]).json()["id"]
    assert client.get(f"/api/jobs/{job_id}/").json()["status"] == "FAILED"


def test_progress_is_committed_after_each_certificate(client, submit, monkeypatch):
    real = pdf.render_certificate
    seen = []

    def spy(path, data):
        # Read the job from a separate session, like a client polling mid-run.
        with client.app.state.session_factory() as s:
            job = s.query(Job).one()
            seen.append((job.status.value, job.completed))
        return real(path, data)

    monkeypatch.setattr(pdf, "render_certificate", spy)
    submit([{"name": "A"}, {"name": "B"}, {"name": "C"}])
    assert seen == [("PROCESSING", 0), ("PROCESSING", 1), ("PROCESSING", 2)]


def test_job_status_reports_progress_fields(client, submit):
    job_id = submit([{"name": "A"}, {"name": ""}]).json()["id"]
    body = client.get(f"/api/jobs/{job_id}/").json()
    assert body["pending"] == 0
    assert body["progress_percent"] == 100.0


def test_unknown_job_is_404(client):
    assert client.get("/api/jobs/doesnotexist/").status_code == 404
