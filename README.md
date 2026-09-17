# TextLab 0.8.1

Patch: CCA import survives background refresh, with persistent error feedback and request-correlated application diagnostics. See [LOGGING.md](LOGGING.md).

## New in 0.8

Import and export CCA Schema 0.1 codebooks from the task library. Category IDs remain output labels; display names, criteria, context, examples and provenance are preserved. See [CCA.md](CCA.md).

## New in 0.7

Fixed evidence-first generation: evidence → candidate interpretations → rationale → labels → confidence (enabled fields). Evidence may refer to competing categories; final labels must match one candidate. Full candidates are stored and alternatives are derived by the backend. No configurable ordering. See [UNCERTAINTY.md](UNCERTAINTY.md).

## New in 0.6

Optional self-reported confidence and structured competing interpretations; per-document seed agreement with durable prediction exports; confidence metrics, reliability and risk–coverage plots with means/SD; live planned query counts and retry ceilings. See [UNCERTAINTY.md](UNCERTAINTY.md).

A self-hosted Python workbench for LLM text classification, multi-task prediction and gold-standard evaluation. FastAPI serves an English web interface; a separate worker sends bounded parallel requests to Ollama or an OpenAI-compatible API such as vLLM. SQLite WAL stores tasks, datasets, job snapshots and results.

## New in 0.5

Five numbered research steps: **Define tasks → Prepare data → Evaluate & refine → Run predictions → Analyze & export**. Corpus and gold datasets are grouped together; Jobs & monitoring is separate, and LLM connections are under Configuration at the bottom of the sidebar.

Contextual shortcuts preselect tasks/datasets, revise evaluated codebooks and transfer evaluated configurations to prediction while preserving task and connection snapshots. The new results hub brings completed reports and downloads together.

See [WORKFLOW.md](WORKFLOW.md) for behavior and upgrade details.

## Included from 0.4

- Inspect and download job error logs while jobs run, including recovered retry failures and raw attempt outputs.
- Set an optional task default label for failed LLM classifications; fallback labels remain explicitly flagged and counted.
- Enter semicolon-separated seeds for evaluation and prediction. Each seed creates an independent run.
- Compare repeated evaluations with means, sample standard deviations and error bars; retain individual runs. Prediction exports identify every task/seed run.

See [REPETITIONS.md](REPETITIONS.md) for workflow, statistical conventions and API examples.

## Core features

- English navigation, forms, feedback, reports and charts. Existing user-authored tasks and texts retain their original language.
- Delete LLM connections, original CSV files, datasets, gold registrations, evaluations and prediction batches. Dependency checks block deletion of active runs; cascade deletion requires confirmation.
- Task-level thinking: server default, disabled, enabled, minimal, low, medium, high or maximum. Model and provider support determines which settings are usable. Jobs and evaluation variants can override task settings.
- Evaluation runtime comparison: active time, elapsed time, document throughput, successful document throughput, mean per-document latency and output-token throughput, alongside quality metrics.
- **Prediction** workspace: select one dataset and multiple tasks. Each task produces an independent job. The worker saves combined CSV, JSON, JSONL, Parquet and manifest files on disk for repeated downloads.

For existing installations, follow [UPGRADE.md](UPGRADE.md). Evaluation details are in [EVALUATION.md](EVALUATION.md), and verification evidence is in [VALIDATION.md](VALIDATION.md).

## Start with Docker

```bash
cp .env.example .env
docker compose up --build -d
```

Open http://localhost:8080. Interactive API documentation: http://localhost:8080/docs.

```bash
docker compose logs -f worker
docker compose down
```

The named volume preserves data. Do not use `docker compose down -v` unless you intend to delete it. The containers call an existing model server; they do not need their own GPU. Compose binds the web port to localhost.

## Start directly with Python (Linux / WSL2)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock
pip install --no-deps -e .
export TEXTLAB_DATA="$PWD/data"
python -m uvicorn textlab.api:app --host 127.0.0.1 --port 8080
```

In a second terminal, in the same project directory:

```bash
source .venv/bin/activate
export TEXTLAB_DATA="$PWD/data"
python -m textlab.worker
```

Both processes must share `TEXTLAB_DATA` and API-key environment variables. Compose loads `.env`; direct Python execution requires explicitly exported variables. Worker locking uses `fcntl`, so use Docker or WSL2 on Windows.

## First prediction

1. **Define tasks → New task:** define categories, instructions, examples and an ambiguity rule. Choose single-label or multi-label classification. Configure rationale, exact evidence quotes and thinking.
2. **Configuration → LLM connections → New connection:** configure your model server. Use **List models** to check it. The demo provider always returns the first category and is only a plumbing test.
3. **Prepare data → Upload CSV:** choose delimiter and encoding; wait for **Ready**.
4. **Run predictions → New prediction:** select the dataset, text column, one or more tasks, connection and model. Use Ctrl/Cmd to select multiple tasks. Advanced parameters can override task settings; by default each task retains its own settings.
5. Open the prediction batch to monitor task runs, pause/resume/cancel, inspect individual results and download persisted exports.

The **Jobs & monitoring** workspace remains available for individual jobs, including child runs belonging to predictions or evaluations.

## Model connections and thinking

| Provider | Example Docker base URL | Thinking mapping |
|---|---|---|
| Ollama native | `http://host.docker.internal:11434` | `think: false`, `true`, or a supported level string |
| OpenAI-compatible / vLLM, Auto or reasoning_effort adapter | `http://host.docker.internal:8000/v1` | `reasoning_effort`; disabled maps to `none`, enabled maps to `medium` |
| OpenAI-compatible, Chat template adapter | Same as above | `chat_template_kwargs.enable_thinking`; on/off only |

**Server default** sends no additional thinking control. Explicit settings that conflict with `extra_body` are rejected. The chat-template adapter rejects graded levels. Ollama rejects `minimal` locally; other unsupported model-level combinations can be rejected by the model server. Selecting disabled does not give a model a capability it lacks: use a model/server that supports the corresponding control. Model lists do not expose a reliable capability matrix.

Returned thinking is saved independently of requested rationale, including when a server returns it despite a disabled request. Ollama `message.thinking`, compatible API `reasoning`, `reasoning_content` or `thinking`, and explicit leading `<think>` blocks are supported. Only text actually returned by the server can be saved. Increase the output-token budget when thinking consumes it.

The profile stores the **name** of an API-key environment variable, not its value. Model IDs can be entered manually. Structured output can use JSON Schema, JSON object or prompt-only instructions; local validation always applies. A host model server must be reachable from the container network; host-only localhost binding may prevent this.

## Task and result schema

Tasks include name, description, mode, unique category labels and definitions, category-specific examples, global multi-label examples, instructions, ambiguity handling, optional empty multi-label selection, rationale, evidence and thinking. For single-label tasks, define a fallback category if needed. Include coding-unit definitions, exclusions and conflict-resolution rules in the instructions.

When evidence and rationale are enabled (candidate comparison and confidence disabled):

```json
{
  "evidence": [{"label": "FOR", "quote": "I support the proposal"}],
  "rationale": "The text explicitly supports the proposal.",
  "labels": ["FOR"]
}
```

Unknown or duplicate labels, invalid cardinality, extra fields and invalid JSON trigger validation errors. Evidence must be an exact contiguous substring of the submitted text, associated with any known codebook label, including competing categories. Validated quotes receive zero-based Unicode character offsets, with an exclusive end; repeated quotes use the first occurrence. This validates quote existence, not semantic relevance. Empty evidence is allowed for decisions based on absence of evidence.

Tasks have revisions. Jobs store immutable task/profile/query snapshots; later edits or deletion of the task or connection do not change those snapshots. Task JSON can be imported through `POST /api/tasks`; there is no separate JSON-import UI.

## Prediction storage and download formats

The worker streams results in batches of 500 into:

```text
TEXTLAB_DATA/
  textlab.sqlite
  <dataset_id>.csv
  predictions/<prediction_id>/
    results.csv
    results.json
    results.jsonl
    results.parquet
    manifest.json
```

Files become downloadable after every task run has completed or cancellation has finished and all exports have been generated. An interrupted export is rebuilt after worker restart; failed exports have a **Retry exports** control. Files remain on disk until the batch or parent dataset is deleted. Generating all formats uses additional disk space and occupies the single worker until finished.

Each export contains **one row per input record, task and seed run**, including failed and unprocessed rows. `job_id`, `task_id`, task name and `row_no` identify the result. Original columns, labels, rationale, evidence, returned thinking, raw response, attempt logs, errors, token counts and per-text duration are retained.

| Format | Representation |
|---|---|
| CSV | UTF-8 BOM; `source.*` and `prediction.*` columns; nested values encoded as JSON strings |
| JSON | Streaming-generated JSON array; original columns nested under `source`; labels and evidence are arrays |
| JSONL | Same structured rows, one JSON object per line |
| Parquet | Zstandard compression; flat columns matching CSV, nested values encoded as JSON strings |
| Manifest | Configuration snapshots, task revisions, job identities and runtime measurements |

CSV prefixes potentially executable spreadsheet formula strings with an apostrophe. JSON/JSONL and Parquet retain raw strings. Input IDs such as `001` remain strings. Unassigned failures use null labels; fallback assignments retain the default label and a fallback flag; valid empty multi-label predictions use `[]`.

Individual classification-job exports retain the previous behavior: completed result rows only, downloaded on demand as CSV/JSONL/Parquet. Prediction exports additionally include unprocessed rows and persist all formats on disk.

## Deletion

- **Delete CSV file** removes the uploaded original while preserving imported database records, gold registrations and results.
- **Delete dataset** removes imported records, the original file and, after confirmation, dependent gold registrations, evaluations, prediction batches, jobs and their results/exports.
- **Delete gold registration** optionally removes its dependent evaluations and their runs. The imported dataset remains.
- **Delete evaluation** removes its runs, predictions and stored report. The gold registration remains.
- **Delete prediction** removes its task runs and saved export directory. The source dataset remains.
- **Delete connection/task** preserves existing job snapshots.

Active, queued or paused dependent jobs must finish or be cancelled and drained before deletion. CSV imports and prediction export generation must finish before their underlying data can be removed. SQLite may retain freed pages for reuse; deleting records does not necessarily shrink the database file immediately.

## Runtime and execution semantics

A single coordinator processes jobs FIFO, with 1–128 request threads per job. A prediction with N tasks over M texts makes N×M classifications, plus retries. More threads do not guarantee higher model throughput.

Active time sums timed worker batches, including API calls, retries and processing overhead. It excludes queue time, pauses, imports and other work between batches. Elapsed time runs from first start to finish and includes pauses. Mean per-document latency includes retries and overlaps across threads; it is not the reciprocal of job throughput. Legacy timing and timing interrupted by an unclean worker shutdown are reported as unknown. Runtime includes model loading and cache effects; use equivalent concurrency, inputs, budgets and warm-up conditions for comparisons.

Pause/cancel stops new submissions and waits for in-flight requests and retries. A crash may repeat an API call whose result was not committed; persisted results are unique per job/input row. `retries=2` permits three total attempts. Transient transport failures, invalid output and HTTP 408/429/5xx retry; other 4xx fail immediately. Empty or overlong texts fail without querying unless explicit truncation is selected.

## Large datasets and operational limits

Uploads stream to disk; imports and prediction exports use bounded batches. Default upload limit is 1 GiB (`TEXTLAB_MAX_UPLOAD_BYTES`). CSV needs a header with unique nonempty column names, consistent column counts and fields no larger than 10 MiB. UTF-8/BOM, UTF-8, CP1252 and Latin-1 are supported. Uploads are not resumable. Interrupted imports restart from the beginning.

A 500 MB input needs more than 500 MB storage: original CSV, database records, results, WAL and every prediction export are additional. Multiple tasks, rationale and thinking can increase storage substantially. RAM use is bounded by batch and output sizes rather than total input rows. Evaluation gold datasets have a separate default 50,000-row limit and at most 50 model configurations.

This is a single-server, trusted-access application. It has no authentication, SSO, per-user quotas, distributed workers, automatic hyperparameter search or global rate limiter. Use local/SSH access or an authenticated reverse proxy. Keep SQLite on a local filesystem. Back up the full data directory with both processes stopped, or use a consistent SQLite backup plus associated files. Lists show the most recent 500 jobs/evaluations/predictions; results use keyset pagination.

## Tests

```bash
pip install -e '.[test]'
python -m pytest -q
```

Optional import benchmark (creates approximately 500 MB of temporary CSV plus database):

```bash
PYTHONPATH=. python tests/benchmark_import.py
```
