import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        storage_dir=tmp_path / "storage",
        max_recipients=50,
    )


@pytest.fixture
def client(settings):
    # TestClient runs background tasks before returning, so a job is finished
    # by the time client.post() comes back.
    with TestClient(create_app(settings)) as c:
        yield c


def make_payload(recipients, **overrides):
    payload = {
        "event_title": "Python Bootcamp 2026",
        "issued_by": "Code Academy",
        "issue_date": "2026-10-01",
        "recipients": recipients,
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def submit(client):
    def _submit(recipients, **overrides):
        return client.post("/api/jobs/", json=make_payload(recipients, **overrides))

    return _submit
