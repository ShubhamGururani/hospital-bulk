# Hospital Bulk Processing API

Uploads a CSV of hospitals, creates each one through the [Hospital Directory API](https://hospital-directory.onrender.com/docs), and activates the whole batch once all of them succeed.

**Live:** https://hospital-bulk-processor-wiac.onrender.com/docs
(Render free tier, so the first request after idling can take ~50s.)

## Run locally

```bash
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Or with Docker:

```bash
docker compose up --build
```

Swagger docs: http://localhost:8000/docs

## Usage

```bash
curl -F file=@samples/hospitals.csv http://localhost:8000/hospitals/bulk
```

CSV format: `name,address,phone` (phone optional, max 20 rows).

| Method | Path | Description |
|---|---|---|
| `POST` | `/hospitals/bulk` | Process a CSV. Add `?background=true` to return immediately and poll |
| `POST` | `/hospitals/bulk/validate` | Validate a CSV without creating anything |
| `GET` | `/hospitals/bulk/{batch_id}` | Batch status and progress |
| `POST` | `/hospitals/bulk/{batch_id}/resume` | Retry failed rows, then activate |
| `GET` | `/health` | Health check |

## How it works

1. The CSV is validated first. If any row is invalid, nothing is created.
2. A UUID batch ID is generated.
3. Hospitals are created concurrently (max 5 in flight) with that batch ID.
4. If every row succeeded, the batch is activated. Otherwise it stays inactive and the failed rows are reported.
5. `resume` retries only the failed rows, so nothing is created twice.

Timeouts, `429` and `5xx` responses are retried with exponential backoff. Other `4xx` errors are not retried.

## Project structure

```
app/
  main.py        App setup and error handlers
  api.py         Routes
  processor.py   Batch workflow
  client.py      Hospital Directory API client with retries
  csv_parser.py  CSV validation
  models.py      Schemas and batch state
  store.py       In-memory batch store
  config.py      Settings from environment variables
tests/           Unit and integration tests (fake upstream, no network)
```

## Tests

```bash
pytest
```

## Limitations

Batch state is kept in memory, so it is lost on restart. In production this would move to Redis or Postgres, and background processing to a task queue.