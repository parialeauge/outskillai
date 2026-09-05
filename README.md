# Pactlify

Admin loads a folder of documents into an in-memory knowledge base. Clients ask a question. Specialist agents retrieve from that KB, optionally search the live web, and return a cited answer plus a PDF.

## Run

From this directory (`outskillai/`):

```bash
python3 -m pip install -e ".[dev]"
uvicorn apps.api.main:app --workers 1
```

Use **one worker**. The knowledge base and job registry are in-process.

Frontend (when built) talks to `http://localhost:8000` by default.

## Environment

Copy `.env.example` to `.env`. Minimum for a local demo:

```
ADMIN_TOKEN=changeme
ALLOWED_INGEST_ROOT=/absolute/path/to/outskillai
```

`ALLOWED_INGEST_ROOT` must be a **parent of** `sample_data/` (the repo root above is fine). Ingest paths are resolved with `resolve(strict=True)` and checked with `os.path.commonpath`, not a string prefix.

Also used when present:

- `OPENROUTER_API_KEY` / `OPENROUTER_MODEL` (default `openai/gpt-4o-mini`)
- `TAVILY_API_KEY` / `NEWSAPI_API_KEY` for live web
- `EMBEDDING_MODEL` (default `sentence-transformers/all-MiniLM-L6-v2`)

## Sample corpus

Paste this folder path into Admin (top-level files only — no subdirectories):

```
<ALLOWED_INGEST_ROOT>/sample_data
```

Contents: `mixed_brief.pdf` (budget page + timeline page), `charter.pdf`, `budget.csv`, `risks.txt`, `urls.txt`.

## Smoke ingest

```bash
python3 -m scripts.smoke_ingest
```
