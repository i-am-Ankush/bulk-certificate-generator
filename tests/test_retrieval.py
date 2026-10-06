import io
import zipfile


def _job_with_one_failure(client, submit):
    job_id = submit([{"name": "Asha Rao"}, {"name": ""}, {"name": "Ravi Kumar"}]).json()["id"]
    certs = client.get(f"/api/jobs/{job_id}/certificates/").json()
    return job_id, certs


def test_list_certificates_with_status_filter(client, submit):
    job_id, certs = _job_with_one_failure(client, submit)
    assert certs["count"] == 3
    assert [c["status"] for c in certs["results"]] == ["COMPLETED", "FAILED", "COMPLETED"]

    failed = client.get(f"/api/jobs/{job_id}/certificates/", params={"status": "FAILED"}).json()
    assert failed["count"] == 1 and failed["results"][0]["download_url"] is None


def test_list_certificates_pagination(client, submit):
    job_id = submit([{"name": f"Person {i}"} for i in range(5)]).json()["id"]
    page = client.get(f"/api/jobs/{job_id}/certificates/", params={"limit": 2, "offset": 2}).json()
    assert page["count"] == 5
    assert [c["index"] for c in page["results"]] == [3, 4]


def test_download_single_certificate(client, submit):
    _, certs = _job_with_one_failure(client, submit)
    url = certs["results"][0]["download_url"]
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")


def test_download_failed_certificate_is_409(client, submit):
    job_id, certs = _job_with_one_failure(client, submit)
    failed_id = certs["results"][1]["id"]
    resp = client.get(f"/api/jobs/{job_id}/certificates/{failed_id}/download/")
    assert resp.status_code == 409


def test_certificate_from_another_job_is_404(client, submit):
    job_a, certs_a = _job_with_one_failure(client, submit)
    job_b = submit([{"name": "Other"}]).json()["id"]
    cert_id = certs_a["results"][0]["id"]
    assert client.get(f"/api/jobs/{job_b}/certificates/{cert_id}/download/").status_code == 404


def test_download_zip_contains_only_generated_certificates(client, submit):
    job_id, _ = _job_with_one_failure(client, submit)
    resp = client.get(f"/api/jobs/{job_id}/download/")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(resp.content)).namelist()
    assert names == ["00001_Asha_Rao.pdf", "00003_Ravi_Kumar.pdf"]


def test_zip_with_nothing_generated_is_409(client, submit):
    job_id = submit([{"name": ""}]).json()["id"]
    assert client.get(f"/api/jobs/{job_id}/download/").status_code == 409
