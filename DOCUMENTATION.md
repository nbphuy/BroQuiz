# BroQuiz Developer Documentation

This is a Windows-first developer runbook for the current BroQuiz backend: FastAPI, `uv`, Docker Desktop, PostgreSQL with pgvector, and Ollama.

## 1. Environment overview

BroQuiz uses `services/api/pyproject.toml` and `services/api/uv.lock` as its primary Python dependency definitions. `services/api/.venv` is the local environment managed by `uv`; do not treat `requirements.txt` as the primary install source. The backend reads repository-root `.env` values (copy from `.env.example` when configuring a new machine).

Current local defaults are PostgreSQL database/user `broquiz`, Compose service `db`, pgvector image `pgvector/pgvector:pg17`, Ollama embedding model `embeddinggemma` (768 dimensions), and Ollama LLM `qwen3:1.7b`.

## 2. Important working directories

Repository root:

```text
<BROQUIZ_ROOT>
```

Backend:

```text
<BROQUIZ_ROOT>\services\api
```

For example, the current checkout is `D:\AI_Engineer\BroQuiz_v1`. Each section states its required location. Run commands from that location: Compose paths and the `.env` file are rooted at the repository, while `uv`, pytest, and Alembic run from `services/api`.

## 3. Quick start

1. Start Docker Desktop.
2. Start PostgreSQL and wait for `db` to become healthy.
3. Confirm Ollama has both required models.
4. Start FastAPI from `services/api`.
5. Open Swagger at <http://127.0.0.1:8000/docs>.

Run from: **repository root**

CMD:

```cmd
docker compose -f infra/compose.yaml up -d
docker compose -f infra/compose.yaml ps
ollama list
```

PowerShell:

```powershell
docker compose -f infra/compose.yaml up -d
docker compose -f infra/compose.yaml ps
ollama list
```

Run from: **services/api**

CMD:

```cmd
uv sync
uv run uvicorn app.main:app --reload
```

PowerShell:

```powershell
uv sync
uv run uvicorn app.main:app --reload
```

The server listens on `http://127.0.0.1:8000` by default. Open <http://127.0.0.1:8000/docs> for Swagger UI or <http://127.0.0.1:8000/openapi.json> for the OpenAPI document. In another terminal, optionally run `uv run pytest -v` from `services/api`.

## 4. Docker and PostgreSQL

Run from: **repository root**

CMD and PowerShell:

```text
docker compose -f infra/compose.yaml up -d          Start db in the background
docker compose -f infra/compose.yaml ps             Show status and health
docker compose -f infra/compose.yaml stop           Stop without removing the volume
docker compose -f infra/compose.yaml restart db     Restart PostgreSQL
docker compose -f infra/compose.yaml logs --tail=100 db
docker compose -f infra/compose.yaml exec db sh     Open a shell in the container
docker compose -f infra/compose.yaml config         Validate/render Compose configuration
```

`docker compose stop` is the normal stop command: the named `broquiz_pgdata` volume remains intact. `docker compose down` removes containers and the network but normally preserves named volumes. **Do not use `docker compose down -v` for routine development or testing**: it removes `broquiz_pgdata` and therefore the local database data. Use it only when intentionally discarding all local PostgreSQL data.

## 5. PostgreSQL and pgvector verification

Run from: **repository root**. The Compose service, database, and user are all `db`, `broquiz`, and `broquiz` respectively (unless overridden in root `.env`).

CMD:

```cmd
docker compose -f infra/compose.yaml exec db pg_isready -U broquiz -d broquiz
docker compose -f infra/compose.yaml exec db psql -U broquiz -d broquiz -c "SELECT current_database(), current_user;"
docker compose -f infra/compose.yaml exec db psql -U broquiz -d broquiz -c "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
docker compose -f infra/compose.yaml exec db psql -U broquiz -d broquiz -c "SELECT '[1,2,3]'::vector;"
docker compose -f infra/compose.yaml exec db psql -U broquiz -d broquiz -c "\dt"
docker compose -f infra/compose.yaml exec db psql -U broquiz -d broquiz -c "SELECT version_num FROM alembic_version;"
```

PowerShell:

```powershell
docker compose -f infra/compose.yaml exec db pg_isready -U broquiz -d broquiz
docker compose -f infra/compose.yaml exec db psql -U broquiz -d broquiz -c "SELECT current_database(), current_user;"
docker compose -f infra/compose.yaml exec db psql -U broquiz -d broquiz -c "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
docker compose -f infra/compose.yaml exec db psql -U broquiz -d broquiz -c "SELECT '[1,2,3]'::vector;"
docker compose -f infra/compose.yaml exec db psql -U broquiz -d broquiz -c "\dt"
docker compose -f infra/compose.yaml exec db psql -U broquiz -d broquiz -c "SELECT version_num FROM alembic_version;"
```

Useful data inspection (the listed tables are the current persisted BroQuiz tables):

SQL:

```sql
SELECT 'documents' AS table_name, count(*) FROM documents
UNION ALL SELECT 'document_chunks', count(*) FROM document_chunks
UNION ALL SELECT 'quizzes', count(*) FROM quizzes
UNION ALL SELECT 'questions', count(*) FROM questions
UNION ALL SELECT 'question_options', count(*) FROM question_options
UNION ALL SELECT 'question_sources', count(*) FROM question_sources
UNION ALL SELECT 'quiz_attempts', count(*) FROM quiz_attempts
UNION ALL SELECT 'attempt_answers', count(*) FROM attempt_answers;
```

Run it with `psql` interactively (`docker compose -f infra/compose.yaml exec db psql -U broquiz -d broquiz`) or pass a single SQL statement with `-c` as above. `document_chunks.embedding` is `vector(768)`.

## 6. Python and uv

Run from: **services/api**

CMD and PowerShell:

```text
uv sync
uv run python --version
uv run pytest
uv run pytest -v
uv run uvicorn app.main:app --reload
```

`uv sync` resolves and installs from `pyproject.toml` and `uv.lock` into `.venv`. It does not add dependencies.

## 7. FastAPI server and route inspection

Run from: **services/api**

CMD and PowerShell:

```text
uv run uvicorn app.main:app --reload
```

Use <http://127.0.0.1:8000/docs>, <http://127.0.0.1:8000/openapi.json>, and `GET /health`. On Windows, `uv run fastapi dev` has previously encountered console encoding/CP1252 output problems; the existing reliable command is `uv run uvicorn app.main:app --reload`.

Swagger is the simplest route inspector. For a terminal route list, use the OpenAPI schema rather than iterating directly over `app.routes`: some FastAPI versions include internal `_IncludedRouter` objects without a `.methods` attribute.

Run from: **services/api**

CMD:

```cmd
uv run python -c "from app.main import app; print(*app.openapi()['paths'].keys(), sep='\n')"
```

PowerShell:

```powershell
uv run python -c "from app.main import app; print(*app.openapi()['paths'].keys(), sep='\n')"
```

## 8. Current endpoint map

| Method | Path | Purpose and precondition |
| --- | --- | --- |
| GET | `/health` | Checks database connectivity; returns `status` and `database`. |
| POST | `/documents` | Uploads and parses a text-based PDF using multipart field `file`. |
| POST | `/documents/{document_id}/chunks` | Chunks a `processed` or already `chunked` document. |
| POST | `/documents/{document_id}/embeddings` | Embeds a `chunked` or already `embedded` document through Ollama. |
| POST | `/documents/{document_id}/search` | Searches an `embedded` document using a query and `top_k`. |
| POST | `/documents/{document_id}/quiz/generate` | Retrieves source chunks using `topic`/`top_k` and generates/persists a grounded quiz for an embedded document. |
| GET | `/quizzes/{quiz_id}` | Database-only retrieval of a persisted quiz; does not invoke Ollama. |
| POST | `/quizzes/{quiz_id}/attempts` | Creates an in-progress attempt with answer-safe questions. |
| POST | `/attempts/{attempt_id}/submit` | Validates stable question/option IDs, scores server-side, and atomically persists the result. |
| GET | `/attempts/{attempt_id}` | Returns answer-safe content while in progress, or review/result content after submission. |

## 9. End-to-end BroQuiz API smoke test

Start the server first. Replace every placeholder such as `<DOCUMENT_ID>` with the ID returned by the preceding response; do not copy placeholders as literal values. The API flow is:

```text
PDF -> Upload -> Chunk -> Embed -> Semantic Search -> Generate Quiz
    -> Get Persisted Quiz -> Start Attempt -> Submit Answers -> Get Result
```

### Health

Run from: any directory

CMD:

```cmd
curl.exe http://127.0.0.1:8000/health
```

PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected success shape:

JSON:

```json
{"status":"ok","database":"ok"}
```

### Upload a PDF

Run from: any directory. The file must be a non-empty valid PDF, has a 25 MiB configured maximum, and must be sent with multipart field name `file`.

CMD:

```cmd
curl.exe -X POST http://127.0.0.1:8000/documents -F "file=@C:\path\to\sample.pdf;type=application/pdf"
```

PowerShell:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/documents -Form @{ file = Get-Item 'C:\path\to\sample.pdf' }
```

`Invoke-RestMethod -Form` requires PowerShell 7 or later. Windows PowerShell users can use the documented `curl.exe` command instead.

The response has `id`, `filename`, `content_type`, `file_size`, `status`, `page_count`, `created_at`, and `updated_at`. Save `id` as `<DOCUMENT_ID>`. A successful parsed upload ends with document status `processed`.

### Chunk the document

Run from: any directory. Current default chunks are 1,800 characters with 250-character overlap; chunking moves a ready document to `chunked`.

CMD:

```cmd
curl.exe -X POST http://127.0.0.1:8000/documents/<DOCUMENT_ID>/chunks
```

PowerShell:

```powershell
$documentId = '<DOCUMENT_ID>'
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/documents/$documentId/chunks"
```

The response contains `document_id`, `status`, `page_count`, and `chunk_count`.

### Create embeddings

Run from: any directory. The configured provider is Ollama, model is `embeddinggemma`, and expected dimension is 768. The endpoint does not return the vectors themselves; it returns `document_id`, `status`, `chunk_count`, `embedded_count`, `model`, and `dimensions`. A success status is `embedded`.

CMD:

```cmd
curl.exe -X POST http://127.0.0.1:8000/documents/<DOCUMENT_ID>/embeddings
```

PowerShell:

```powershell
$documentId = '<DOCUMENT_ID>'
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/documents/$documentId/embeddings"
```

### Semantic search

Run from: any directory. The body is `query` plus optional `top_k`. The configured default is 5 and the maximum is 20. Results are scoped to the document and ranked by pgvector cosine distance. The response reports `similarity` as `1 - cosine_distance`, so higher values are more similar. Each result includes `chunk_id`, `document_id`, `page_number`, `chunk_index`, `content`, and `similarity`; response metadata includes the result count, embedding model, and dimensions.

CMD:

```cmd
curl.exe -X POST "http://127.0.0.1:8000/documents/<DOCUMENT_ID>/search" -H "Content-Type: application/json" -d "{\"query\":\"Human-computer interaction\",\"top_k\":5}"
```

PowerShell:

```powershell
$documentId = '<DOCUMENT_ID>'
$body = @{ query = 'Human-computer interaction'; top_k = 5 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/documents/$documentId/search" -ContentType 'application/json' -Body $body
```

### Generate and persist a local quiz

Run from: any directory. Quiz generation calls the same document-scoped pgvector retrieval service used by semantic search, asks the configured Ollama text-generation model (`qwen3:1.7b` by default) for schema-constrained output, validates the complete quiz and cited chunks, then commits the quiz graph atomically. Retrieved document text is delimited and treated as untrusted source data rather than model instructions. The body has `topic`, optional `question_count` (default 5, range 1–10), and optional `top_k` (default 5, range 1–20).

CMD:

```cmd
curl.exe -X POST "http://127.0.0.1:8000/documents/<DOCUMENT_ID>/quiz/generate" -H "Content-Type: application/json" -d "{\"topic\":\"Human-computer interaction\",\"question_count\":3,\"top_k\":5}"
```

PowerShell:

```powershell
$documentId = '<DOCUMENT_ID>'
$body = @{ topic = 'Human-computer interaction'; question_count = 3; top_k = 5 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/documents/$documentId/quiz/generate" -ContentType 'application/json' -Body $body
```

The response includes persisted `id` (save it as `<QUIZ_ID>`), `document_id`, `title`, `topic`, `status`, and `questions`. Each quiz question has `question`, exactly four unique nonblank `options`, one valid `correct_answer` index, `explanation`, and retrieved-source provenance (`chunk_id`, `page_number`, optional `chunk_index`). Duplicate questions, fabricated citations, malformed structured output, and partial quizzes are rejected.

### Get the persisted quiz

Run from: any directory. This performs database retrieval only and should not invoke Ollama.

CMD:

```cmd
curl.exe http://127.0.0.1:8000/quizzes/<QUIZ_ID>
```

PowerShell:

```powershell
$quizId = '<QUIZ_ID>'
Invoke-RestMethod "http://127.0.0.1:8000/quizzes/$quizId"
```

### Start an attempt

Run from: any directory. There is no request body. Multiple attempts are allowed for a quiz. The `201` response has `id` (save as `<ATTEMPT_ID>`), `quiz_id`, `title`, `topic`, `status`, `total_questions`, `started_at`, and ordered `questions`; ordered question options have stable `id`, `position`, and `text`.

The start/read contract is answer-safe. Before completion it contains no correct option information, correctness flags, explanations, or source citations. The player must use option `id` for submission identity; `position` is display metadata only.

CMD:

```cmd
curl.exe -X POST http://127.0.0.1:8000/quizzes/<QUIZ_ID>/attempts
```

PowerShell:

```powershell
$quizId = '<QUIZ_ID>'
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/quizzes/$quizId/attempts"
```

### Submit answers

Run from: any directory. Get each `question_id` and `option_id` from the answer-safe attempt response. Include every quiz question exactly once. The client submits neither correctness nor score; extra fields are rejected and the backend resolves the option, computes correctness, and scores the attempt.

CMD:

```cmd
curl.exe -X POST "http://127.0.0.1:8000/attempts/<ATTEMPT_ID>/submit" -H "Content-Type: application/json" -d "{\"answers\":[{\"question_id\":\"<QUESTION_ID_1>\",\"option_id\":\"<OPTION_ID_1>\"},{\"question_id\":\"<QUESTION_ID_2>\",\"option_id\":\"<OPTION_ID_2>\"}]}"
```

PowerShell:

```powershell
$attemptId = '<ATTEMPT_ID>'
$body = @{
    answers = @(
        @{ question_id = '<QUESTION_ID_1>'; option_id = '<OPTION_ID_1>' }
        @{ question_id = '<QUESTION_ID_2>'; option_id = '<OPTION_ID_2>' }
    )
} | ConvertTo-Json -Depth 4
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/attempts/$attemptId/submit" -ContentType 'application/json' -Body $body
```

The submitted response contains `id`, `quiz_id`, `status`, `score`, `total_questions`, `started_at`, `submitted_at`, and per-answer `question_id`, `selected_answer`, `correct_answer`, `is_correct`, `explanation`, and `sources`.

### Get an attempt result

Run from: any directory.

CMD:

```cmd
curl.exe http://127.0.0.1:8000/attempts/<ATTEMPT_ID>
```

PowerShell:

```powershell
$attemptId = '<ATTEMPT_ID>'
Invoke-RestMethod "http://127.0.0.1:8000/attempts/$attemptId"
```

An `in_progress` attempt returns the answer-safe representation (`questions` and options, no correct answer). A `submitted` attempt returns the persisted review/results representation including score, correctness, explanations, and sources.

The M7 UI starts at `/quizzes/{quiz_id}/play` and routes a successful start to `/attempts/{attempt_id}`. Selections are local until the user finishes because the established attempt architecture persists the complete answer set atomically. Reloading a valid in-progress attempt safely restores its quiz questions, but not unsubmitted local selections. Reloading a submitted attempt shows only a neutral completion state; M8 will own review presentation.

Expected lifecycle and validation errors:

- `404`: quiz or attempt does not exist;
- `409`: quiz has no questions, or the attempt is already submitted/not editable;
- `422`: missing or duplicate questions, a question outside the attempt quiz, an option outside its question/quiz, malformed IDs, or client-supplied extra answer fields.

Every question is required. A submission is one transaction: any persistence failure rolls back the answer rows and leaves the attempt `in_progress`.

## 10. Ollama, EmbeddingGemma, and qwen

Run from: any directory. Start the Ollama application/service before these commands.

CMD:

```cmd
ollama list
ollama pull embeddinggemma
ollama pull qwen3:1.7b
ollama run qwen3:1.7b "Reply with exactly: BroQuiz LLM OK"
curl.exe http://localhost:11434/api/tags
curl.exe -X POST http://localhost:11434/api/embed -H "Content-Type: application/json" -d "{\"model\":\"embeddinggemma\",\"input\":\"Human computer interaction\"}"
```

PowerShell:

```powershell
ollama list
ollama pull embeddinggemma
ollama pull qwen3:1.7b
ollama run qwen3:1.7b "Reply with exactly: BroQuiz LLM OK"
Invoke-RestMethod http://localhost:11434/api/tags
$body = @{
    model = 'embeddinggemma'
    input = 'Human computer interaction'
} | ConvertTo-Json
$response = Invoke-RestMethod -Method Post -Uri http://localhost:11434/api/embed -ContentType 'application/json' -Body $body
$response.embeddings[0].Count
```

The embedding smoke test should report 768 values, matching `EMBEDDING_DIMENSIONS=768`. `ollama list` should show both configured model names. Retrieval always uses `EMBEDDING_MODEL` (`embeddinggemma`); quiz generation separately uses `OLLAMA_LLM_MODEL` (`qwen3:1.7b`). `LLM_PROVIDER` remains `ollama`. Do not paste escaped `\"` sequences into a PowerShell single-quoted string; build JSON with `ConvertTo-Json` as shown.

## 11. Testing and opt-in integration tests

Run from: **services/api**

CMD:

```cmd
uv run pytest
uv run pytest -v
uv run pytest tests/test_embedding_service.py -v
uv run pytest tests/test_quiz_service.py tests/test_llm_provider.py tests/test_document_api.py -v
uv run pytest tests/test_attempt_api.py -v
set BROQUIZ_RUN_INTEGRATION=1 && uv run pytest -v
set BROQUIZ_RUN_INTEGRATION=1 && uv run pytest tests/test_retrieval_integration.py -v
set BROQUIZ_RUN_INTEGRATION=1 && uv run pytest tests/test_quiz_integration.py -v
set BROQUIZ_RUN_INTEGRATION=1 && uv run pytest tests/test_attempt_integration.py -v
set BROQUIZ_RUN_INTEGRATION=
```

PowerShell:

```powershell
uv run pytest
uv run pytest -v
uv run pytest tests/test_embedding_service.py -v
uv run pytest tests/test_quiz_service.py tests/test_llm_provider.py tests/test_document_api.py -v
uv run pytest tests/test_attempt_api.py -v
$env:BROQUIZ_RUN_INTEGRATION = '1'; uv run pytest -v
$env:BROQUIZ_RUN_INTEGRATION = '1'; uv run pytest tests/test_retrieval_integration.py -v
$env:BROQUIZ_RUN_INTEGRATION = '1'; uv run pytest tests/test_quiz_integration.py -v
$env:BROQUIZ_RUN_INTEGRATION = '1'; uv run pytest tests/test_attempt_integration.py -v
Remove-Item Env:BROQUIZ_RUN_INTEGRATION
```

Normal tests use fakes or an in-memory SQLite database and do not require live PostgreSQL/Ollama. `tests/test_attempt_api.py` covers the ordinary M7 lifecycle without Ollama, embeddings, or pgvector. Real integration tests are skipped unless `BROQUIZ_RUN_INTEGRATION=1` and require their local infrastructure: `tests/test_retrieval_integration.py`, `tests/test_quiz_integration.py`, and `tests/test_attempt_integration.py`. The retrieval and quiz integration tests need PostgreSQL and Ollama; the attempt integration test needs PostgreSQL. They create and clean up their own temporary test records (and upload fixture files where applicable).

Frontend M7 verification runs from **apps/broquiz**. Start the FastAPI server before regenerating types; on Windows PowerShell systems that block `npm.ps1`, use `npm.cmd`:

```powershell
npm.cmd run api:generate
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run test
npm.cmd run build
```

## 12. Alembic migrations

Run from: **services/api**

CMD and PowerShell:

```text
uv run alembic current
uv run alembic history
uv run alembic check
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "describe model change"
```

`current` reports the database revision, `history` shows migration order, `check` detects model metadata changes that would produce an autogenerated migration, and `upgrade head` applies outstanding revisions. Generate a revision only after a deliberate SQLAlchemy model change—**not** merely to test the application. Review generated revisions before applying them.

For a deliberate, reviewed rollback, target the preceding revision explicitly, for example `uv run alembic downgrade d4e5f6a7b8c9` (this removes the quiz-attempt migration). Do not use database/volume resets as migration troubleshooting.

Current migration chain:

1. `b9b2247fcba7` — `create document tables`
2. `c3d4e5f6a7b8` — `add chunk embeddings`
3. `d4e5f6a7b8c9` — `add quiz persistence`
4. `e5f6a7b8c9d0` — `add quiz attempts` (current head)

## 13. Git safety checks and ignore policy

Run from: **repository root**

CMD:

```text
git rev-parse --show-toplevel
git status
git diff --stat
git diff
git ls-files | findstr /i "__pycache__ .pyc .pyo"
```

PowerShell:

```powershell
git rev-parse --show-toplevel
git status
git diff --stat
git diff
git ls-files | Select-String -Pattern '(^|/)__pycache__/|\.py[co]$'
```

Before committing backend work, inspect `git status` and ensure no unintended files below `apps/` are included. The frontend is a nested repository, so inspect its own status only after confirming the directory/repository context. Never blindly run `git restore .`; first use `git rev-parse --show-toplevel`, inspect the exact changes, and restore only a confirmed unwanted path.

The current `.gitignore` covers `.env`/`.env.*` (while keeping `.env.example`), `.venv/`, Python caches (`__pycache__/`, `*.py[cod]`, `.pytest_cache/`), Node/Next output (`node_modules/`, `.next/`, `out/`, `coverage/`, logs), and uploaded files under `data/uploads/*` except `.gitkeep`. `.gitignore` does not stop Git tracking a file that was already committed; use `git ls-files` to detect that situation.

## 14. Troubleshooting

**Swagger does not show a new endpoint.** Inspect `app.openapi()['paths']` with the command in section 7, confirm the router is included in `app/main.py`, restart Uvicorn, then hard-refresh Swagger.

**Uvicorn runs but does not print every GET/POST route.** Normal. Inspect `/docs` or the OpenAPI schema; route logging is not the authoritative route list.

**`AttributeError: '_IncludedRouter' object has no attribute 'methods'`.** Do not inspect every `app.routes` object as though it were a route. Use `app.openapi()['paths']`.

**Integration tests are `SKIPPED`.** This is expected unless the opt-in flag is exactly `1`.

CMD:

```cmd
set BROQUIZ_RUN_INTEGRATION=1 && uv run pytest -v
```

PowerShell:

```powershell
$env:BROQUIZ_RUN_INTEGRATION = '1'; uv run pytest -v
```

**Database connection fails or `/health` returns 503.** Confirm Docker Desktop is running, then run `docker compose -f infra/compose.yaml ps` from the repository root. Wait for `db` to report healthy and verify it with `pg_isready` from section 5. Confirm root `.env` agrees with the Compose database/user/password/port values.

**Ollama is unavailable.** Run `ollama list` and `Invoke-RestMethod http://localhost:11434/api/tags` (or the CMD `curl.exe` equivalent). Start the Ollama application/service, then pull `embeddinggemma` and `qwen3:1.7b` if absent.

**Quiz generation returns 503.** Confirm `LLM_PROVIDER=ollama`, verify `OLLAMA_BASE_URL`, and make sure the exact `OLLAMA_LLM_MODEL` value appears in `ollama list`. The generation model is separate from `embeddinggemma`; an embedding-only installation can search but cannot generate quizzes.

**Quiz generation returns 502.** The text-generation model returned malformed or domain-invalid structured output, such as the wrong question count, duplicate choices/questions, or source references outside the retrieved chunks. Retry once; if it persists, inspect server logs and verify the configured model supports Ollama JSON-schema output. API responses intentionally omit raw prompts and provider details.

**Embedding dimension error.** The backend and migration expect 768 dimensions. Verify `EMBEDDING_MODEL=embeddinggemma` and `EMBEDDING_DIMENSIONS=768`, then run the `/api/embed` smoke test and check `$response.embeddings[0].Count`.

**`uv run fastapi dev` hits Windows console encoding/CP1252 output trouble.** Use the existing working server command: `uv run uvicorn app.main:app --reload`.

**Docker or uv reports cache/sandbox permission messages.** Distinguish tooling permissions from application failure: first check whether Compose reports a healthy `db`, whether `/health` succeeds, and whether `uv run pytest` actually fails. A sandbox/cache warning alone does not prove the FastAPI application, PostgreSQL, or Ollama integration is broken.

## 15. Full backend verification checklist

- [ ] Docker Desktop is running and `docker compose -f infra/compose.yaml ps` reports `db` healthy.
- [ ] PostgreSQL connects as `broquiz` to database `broquiz`; `vector` extension and `SELECT '[1,2,3]'::vector;` succeed.
- [ ] Ollama is available; `embeddinggemma` and `qwen3:1.7b` appear in `ollama list`.
- [ ] EmbeddingGemma API smoke test returns 768 dimensions.
- [ ] `uv run pytest` passes from `services/api`.
- [ ] Opt-in integration tests pass with `BROQUIZ_RUN_INTEGRATION=1` when local dependencies are available.
- [ ] `uv run alembic check` is clean and `uv run alembic current` is at `e5f6a7b8c9d0` after applying migrations.
- [ ] `GET /health` returns HTTP 200 and `GET /docs` loads.
- [ ] The ten current endpoint paths appear in OpenAPI.
- [ ] The end-to-end PDF-to-attempt flow works with a local text-based PDF.
- [ ] `git status` contains no accidental frontend changes under `apps/`.
