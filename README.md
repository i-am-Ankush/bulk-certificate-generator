# Bulk Certificate Generator

A FastAPI backend that accepts **one request containing many recipients**, generates a PDF
certificate for each from a single predefined template, tracks progress, and lets the client
download the results (one by one, or as a ZIP).

- **Stack:** Python 3.10+, FastAPI, SQLAlchemy 2, SQLite (Postgres-ready), ReportLab, pytest
- **Processing:** background task (the POST returns `202` immediately; the client polls the job)

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
```

## Run

```bash
uvicorn app.main:create_app --factory --reload
```

Interactive docs: http://127.0.0.1:8000/docs

Configuration (environment variables, all optional):

| Variable         | Default                  | Meaning                            |
|------------------|--------------------------|------------------------------------|
| `DATABASE_URL`   | `sqlite:///./certgen.db` | Any SQLAlchemy URL                 |
| `STORAGE_DIR`    | `./storage`              | Where generated PDFs are written   |
| `MAX_RECIPIENTS` | `1000`                   | Max recipients allowed per request |

To use PostgreSQL: `pip install "psycopg[binary]"` and set
`DATABASE_URL=postgresql+psycopg://user:pass@localhost/certgen`.

## Run the tests

```bash
pytest
```

## API

| Method | Path                                             | Purpose                                       |
|--------|--------------------------------------------------|-----------------------------------------------|
| POST   | `/api/jobs/`                                     | Submit a bulk generation request (202)        |
| GET    | `/api/jobs/{id}/`                                | Status, progress counts, list of failures     |
| GET    | `/api/jobs/{id}/certificates/`                   | List certificates (`?status=`, `limit`, `offset`) |
| GET    | `/api/jobs/{id}/certificates/{cert_id}/download/`| Download one PDF                              |
| GET    | `/api/jobs/{id}/download/`                       | ZIP of all certificates generated so far      |

### Submit a request

```bash
curl -X POST http://127.0.0.1:8000/api/jobs/ \
  -H "Content-Type: application/json" \
  -d '{
    "event_title": "Python Bootcamp 2026",
    "issued_by": "Code Academy",
    "issue_date": "2026-10-01",
    "recipients": [
      {"name": "Asha Rao", "email": "asha@example.com", "achievement": "Top Scorer"},
      {"name": "Ravi Kumar"},
      {"name": ""}
    ]
  }'
```

`issue_date` is optional (defaults to today). Per recipient: `name` is required (max 100 chars);
`email` and `achievement` are optional. Response (`202 Accepted`):

```json
{
  "id": "fe202e78100047749ecc360917cfd6e9",
  "status": "PENDING",
  "total": 3, "completed": 0, "failed": 1, "pending": 2,
  "progress_percent": 33.3,
  "links": {
    "self": "/api/jobs/fe202e78.../",
    "certificates": "/api/jobs/fe202e78.../certificates/",
    "download_all": "/api/jobs/fe202e78.../download/"
  }
}
```

### Check progress

```bash
curl http://127.0.0.1:8000/api/jobs/<id>/
```

```json
{
  "status": "COMPLETED_WITH_ERRORS",
  "total": 3, "completed": 2, "failed": 1, "pending": 0, "progress_percent": 100.0,
  "failures": [
    {"index": 3, "recipient_name": "(unnamed)", "error": "name: String should have at least 1 character"}
  ]
}
```

Job statuses: `PENDING` → `PROCESSING` → `COMPLETED` (all ok) | `COMPLETED_WITH_ERRORS`
(some failed) | `FAILED` (none generated).

### Retrieve certificates

```bash
curl http://127.0.0.1:8000/api/jobs/<id>/certificates/?status=COMPLETED   # list + download_url
curl -OJ http://127.0.0.1:8000/api/jobs/<id>/certificates/<cert_id>/download/   # one PDF
curl -OJ http://127.0.0.1:8000/api/jobs/<id>/download/                          # ZIP
```

Errors: `404` unknown job/certificate, `409` asking for a file that does not exist
(failed certificate, or a ZIP with nothing generated yet), `422` invalid request.

## Design decisions

**Validation happens in two layers.** Request-level fields (`event_title`, `issued_by`, a
non-empty `recipients` list, size limit) are strict and return `422`. Each recipient is then
validated *individually* when the job is created. Invalid recipients are stored as `FAILED`
certificates with a reason, valid ones are queued. So one bad row never rejects the batch, and
the client sees exactly which rows failed and why.

**Background processing via FastAPI `BackgroundTasks`.**
- *Synchronous* was rejected: 1,000 PDFs in one HTTP request risks timeouts and blocks the client.
- *Celery/RQ + Redis* is the production answer (survives restarts, scales across workers) but
  adds a broker and a worker process for a task this size.
- `BackgroundTasks` keeps the project to one process and still gives the async contract
  (`202` + polling). The cost is that a job in flight is lost if the server restarts
  (see Limitations). The processing function only takes a job id, so moving it to Celery later
  is a small change.

**Per-certificate isolation and progress.** Each certificate is rendered inside its own
`try/except` and committed individually. A failure marks only that row `FAILED` (and deletes any
partial file); progress counters are visible to pollers while the job runs. If something
infrastructure-level breaks mid-job, the job is marked `FAILED` rather than left `PROCESSING`.

**Relational model.** `jobs` (counts, status, shared certificate fields) and `certificates`
(one row per recipient: index, status, error, relative file path). Counters live on the job so
status checks are a single-row read. Files are stored on disk under `STORAGE_DIR/<job_id>/`,
with paths stored relative so the storage directory can be moved.

**ReportLab for the template.** Pure Python, no system dependencies, fast. All checks (font
coverage, text fit) run before the file is written, so failures never leave partial PDFs.

**App factory (`create_app`).** Settings, engine and session factory are created per app
instance, which keeps tests isolated (each test gets its own SQLite file and storage dir).

## Limitations and future scope

- **Restart safety:** pending certificates of an interrupted job are not resumed. Next step:
  a Celery/RQ worker, or a startup task that re-queues `PENDING`/`PROCESSING` jobs.
- **Non-Latin names:** the built-in PDF fonts cannot render e.g. Devanagari; those recipients
  fail with a clear error instead of printing blanks. Fix: embedding a Noto TTF alone is
  insufficient because ReportLab lacks complex text shaping for matras and conjuncts.
  Full support requires text shaping (e.g. HarfBuzz via `uharfbuzz`) or an HTML-to-PDF
  engine like WeasyPrint.
- **Auth, rate limiting, idempotency keys** (to avoid duplicate jobs on client retries).
- **Email delivery** of certificates using the optional `email` field; webhooks on completion.
- **Cloud storage (S3)** instead of local disk; Alembic migrations instead of `create_all`.
- **Configurable template** (logo, colors) once more than one design is needed.
