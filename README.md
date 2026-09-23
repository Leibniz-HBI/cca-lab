# CCA-Lab

A Python workbench for reproducible LLM-based content analysis using CCA Schema codebooks.

## Core features

- English navigation, forms, feedback, reports and charts. Existing user-authored tasks and texts retain their original language.
- Delete LLM connections, original CSV files, datasets, gold registrations, evaluations and prediction batches. Dependency checks block deletion of active runs; cascade deletion requires confirmation.
- Experiment configurations: vary models, sampling parameters, context, output fields, thinking, joint/binary classification and batch size. Defaults: 8192 output tokens, 3 retries, seed 9721. See [EXPERIMENTS.md](EXPERIMENTS.md).
- Prompt compiler comparison: user/assistant demonstrations or annotated reference examples in one system message. Compare both as experiment variants. Shared readable/JSON viewers with syntax highlighting support previews and logs.
- Sort result tables by clicking column headers (click again to reverse). Numeric means sort numerically, unavailable values remain last, and sort choices survive table refreshes. Sorting also works in downloaded HTML reports.
- Individual-run error statistics: frequencies by exact error message, affected documents and final outcomes (recovered, failed, fallback). Counts include failed document/category attempts from committed results, not distinct HTTP requests; documents may occur under multiple messages. Detailed error logs remain available.
- Evaluation runtime comparison: active time, elapsed time, document throughput, successful document throughput, mean per-document latency and output-token throughput, alongside quality metrics.
- **Prediction** workspace: select one dataset and multiple tasks. Each task produces an independent job. The worker saves combined CSV, JSON, JSONL, Parquet and manifest files on disk for repeated downloads.

For installation and updating from 0.13.0, see [UPGRADE.md](UPGRADE.md). Evaluation details are in [EVALUATION.md](EVALUATION.md), and verification evidence is in [VALIDATION.md](VALIDATION.md).

## Scheduling and evaluation details (0.13.1)

Jobs on different server endpoints now execute concurrently (up to eight active endpoints). Jobs sharing the same URL scheme, hostname and port remain serialized, even across different connection profiles or API paths. Each job retains its configured request concurrency. Host aliases pointing at the same physical server cannot be detected automatically; reuse one hostname if they should share capacity. Imports and report/export generation still occupy the coordinator between request windows.

Evaluation details show the model and connection from each immutable job snapshot. Delayed detail/report responses cannot overwrite another dialog session. Switching connections immediately clears the available-model selection; choose models explicitly after loading. Existing generated configurations retain their original connection and are identified in the review table.

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
export CCA_LAB_DATA="$PWD/data"
python -m uvicorn cca_lab.api:app --host 127.0.0.1 --port 8080
```

In a second terminal, in the same project directory:

```bash
source .venv/bin/activate
export CCA_LAB_DATA="$PWD/data"
python -m cca_lab.worker
```

Both processes must share `CCA_LAB_DATA` and API-key environment variables. Compose loads `.env`; direct Python execution requires explicitly exported variables. Worker locking uses `fcntl`, so use Docker or WSL2 on Windows.

## First prediction

1. **Define tasks → New task:** create a CCA codebook with title, description, categories, instructions and examples. Choose single-label or multi-label classification. Execution settings belong to job configurations.
2. **Configuration → LLM connections → New connection:** configure your model server. Use **List models** to check it. The demo provider always returns the first category and is only a plumbing test.
3. **Prepare data → Upload CSV:** choose delimiter and encoding; wait for **Ready**.
4. **Run predictions → New prediction:** select the dataset, text and optional context columns, and one or more tasks. Generate and review experiment configurations before starting. Use comma-separated parameters and Off/On/Compare both controls to create variations; comma-separated seeds repeat each configuration.
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

Tasks contain a standards-compliant `codebook`, with identity, version, description, instructions, unit of analysis, classification mode, categories and examples. Category `id` is the prediction value; `label` is the display name. All examples are standard top-level CCA examples. Rationale, evidence, confidence, alternative interpretations, thinking and fallback settings belong to experiment configurations. Multi-label tasks accept empty label sets. Include ambiguity handling in coding instructions or category notes. See [CCA.md](CCA.md).

When evidence and rationale are enabled (candidate comparison and confidence disabled):

```json
{
  "evidence": [{"label": "FOR", "quote": "I support the proposal"}],
  "rationale": "The text explicitly supports the proposal.",
  "labels": ["FOR"]
}
```

Unknown or duplicate labels, invalid cardinality, extra fields and invalid JSON trigger validation errors. Evidence must be an exact contiguous substring of the submitted text, associated with any known codebook label, including competing categories. Validated quotes receive zero-based Unicode character offsets, with an exclusive end; repeated quotes use the first occurrence. This validates quote existence, not semantic relevance. Empty evidence is allowed for decisions based on absence of evidence.

Tasks have revisions. Jobs store immutable task/profile/query snapshots; later edits or deletion of the task or connection do not change those snapshots. Native CCA-Lab task JSON can be imported through `POST /api/tasks`. The file-import UI accepts standard CCA codebook JSON.

## Prediction storage and download formats

The worker streams results in batches of 500 into:

```text
CCA_LAB_DATA/
  cca_lab.sqlite
  <dataset_id>.csv
  predictions/<prediction_id>/
    results.csv
    results.json
    results.jsonl
    results.parquet
    manifest.json
    requests.jsonl
```

Files become downloadable after every task run has completed or cancellation has finished and all exports have been generated. An interrupted export is rebuilt after worker restart; failed exports have a **Retry exports** control. Files remain on disk until the batch or parent dataset is deleted. Generating all formats uses additional disk space and occupies the coordinator until finished; already dispatched request windows on other servers can finish meanwhile.

Each export contains **one row per input record, task, configuration and seed run**, including failed and unprocessed rows. `job_id`, `task_id`, task name and `row_no` identify the result. Original columns, labels, rationale, evidence, component decisions, attempt references and errors are retained. Exact requests, raw responses, returned thinking and token usage are stored once per request in requests.jsonl. Document token fields are zero because shared tokens are not attributed to individual documents; allocated document duration is an equal share of request time, not isolated latency.

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

A single coordinator processes jobs FIFO, with 1–128 request threads per job. A prediction crosses tasks, configurations and seeds. Nominal requests per run are ceil(documents / batch_size), multiplied by category count in binary mode. Character-based splits and retries can increase this count. More threads do not guarantee higher model throughput.

Active time sums timed worker batches, including API calls, retries and processing overhead. It excludes queue time, pauses, imports and other work between batches. Elapsed time runs from first start to finish and includes pauses. Mean per-document latency includes retries and overlaps across threads; it is not the reciprocal of job throughput. Timing interrupted by an unclean worker shutdown are reported as unknown. Runtime includes model loading and cache effects; use equivalent concurrency, inputs, budgets and warm-up conditions for comparisons.

Pause/cancel stops new submissions and waits for in-flight requests; unresolved retries resume later. A crash may repeat an API call whose result was not committed; persisted results are unique per job/input row. The default `retries=3` permits four total attempts. Transient transport failures, invalid output and HTTP 408/429/5xx retry; other 4xx fail immediately. Empty or overlong texts fail without querying unless explicit truncation is selected.

## Large datasets and operational limits

Uploads stream to disk; imports and prediction exports use bounded batches. Default upload limit is 1 GiB (`CCA_LAB_MAX_UPLOAD_BYTES`). CSV needs a header with unique nonempty column names, consistent column counts and fields no larger than 10 MiB. UTF-8/BOM, UTF-8, CP1252 and Latin-1 are supported. Uploads are not resumable. Interrupted imports restart from the beginning.

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
