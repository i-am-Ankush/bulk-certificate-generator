import pytest

from tests.conftest import make_payload


@pytest.mark.parametrize(
    "overrides",
    [
        {"recipients": []},
        {"event_title": ""},
        {"issued_by": "   "},
        {"issue_date": "not-a-date"},
    ],
)
def test_request_level_validation_rejects_bad_payload(client, overrides):
    payload = make_payload([{"name": "Asha"}])
    payload.update(overrides)
    resp = client.post("/api/jobs/", json=payload)
    assert resp.status_code == 422


def test_missing_required_field_is_422(client):
    resp = client.post("/api/jobs/", json={"event_title": "X", "recipients": [{"name": "A"}]})
    assert resp.status_code == 422


def test_too_many_recipients_is_422(submit):
    resp = submit([{"name": f"Person {i}"} for i in range(51)])  # limit is 50 in tests
    assert resp.status_code == 422
    assert "At most 50" in resp.json()["detail"]


def test_invalid_recipients_fail_individually_and_valid_ones_still_run(client, submit):
    resp = submit(
        [
            {"name": "Asha Rao"},  # 1 ok
            {"name": ""},  # 2 empty name
            {"email": "no-name@example.com"},  # 3 missing name
            {"name": "Ravi", "email": "not-an-email"},  # 4 bad email
            "just a string",  # 5 not an object
            {"name": "Meena", "email": "meena@example.com", "achievement": "Top Scorer"},  # 6 ok
        ]
    )
    assert resp.status_code == 202
    body = client.get(f"/api/jobs/{resp.json()['id']}/").json()

    assert body["status"] == "COMPLETED_WITH_ERRORS"
    assert (body["total"], body["completed"], body["failed"]) == (6, 2, 4)
    assert [f["index"] for f in body["failures"]] == [2, 3, 4, 5]
    errors = {f["index"]: f["error"] for f in body["failures"]}
    assert "name" in errors[2]
    assert "Field required" in errors[3]
    assert "valid email" in errors[4]


def test_all_recipients_invalid_marks_job_failed(client, submit):
    resp = submit([{"name": ""}, {"nope": 1}])
    assert resp.status_code == 202
    body = client.get(f"/api/jobs/{resp.json()['id']}/").json()
    assert body["status"] == "FAILED"
    assert body["completed"] == 0 and body["failed"] == 2
