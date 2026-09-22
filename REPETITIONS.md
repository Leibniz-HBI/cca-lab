# Error logs, fallback labels and repeated seed runs

## Inspecting job errors

Open a classification job and select **Inspect errors**, or expand **Error log**. This works during processing and after completion. Use **Load / refresh error log**, **Next 50** and **Include recovered retry errors** to inspect final failures, fallback assignments and failed attempts that later succeeded.

Each entry includes the input row and source data, final outcome, assigned fallback label if any, error message, attempt count, raw model outputs, returned thinking and per-attempt errors. Newly created attempt records include a start timestamp. No credentials are stored in the log. HTTP failures show the status code; arbitrary HTTP error response bodies are not persisted. An in-flight attempt appears only after its row result is committed. A worker-level interruption remains visible as the latest job error; its Python traceback stays in the worker process log.

**Download JSONL** streams error records without requiring the job to finish. For a running job this is a live export, not a frozen snapshot. Error browsing uses a partial index and keyset pagination rather than loading the complete dataset.

```text
GET /api/jobs/{id}/errors?after=0&limit=50&include_recovered=true
GET /api/jobs/{id}/errors?format=jsonl&include_recovered=false
```

The JSON response contains `rows`, `total`, `next_after`, `status` and `last_error`. Row errors include `attempt_outputs`, `error_count`, `fallback_used` and `source`.

## Default fallback label

Set **Default label after failed LLM attempts** in an experiment configuration to one of the task’s category IDs. Leave it empty to retain the previous failure behavior. For multi-label tasks the configured fallback is a singleton label set, not a new category or an inferred label combination.

After an attempted LLM classification ends without a valid response, TextLab assigns that label with `status="fallback"` and `fallback_used=true`. Retries retain their existing semantics: `retries=2` allows three attempts; non-retryable HTTP errors terminate earlier. Raw responses, returned thinking and errors are preserved. No rationale or evidence is fabricated for the fallback.

Rejected empty/overlong inputs and unprocessed or cancelled rows do not receive fallback labels. A valid response always takes precedence over the fallback. Existing job snapshots are unchanged if you later change configuration settings.

Job failure counts include fallback assignments, with `fallback_count` identifying that subset. Such jobs remain **Completed with errors**. Individual-job and prediction exports retain both the assigned label and its flagged provenance.

Evaluations score fallback labels as the system's assigned output:

- `coverage`: valid model responses / all gold documents, excluding fallbacks.
- `output_coverage`: assigned model or fallback predictions / all gold documents.
- `fallback_n`: records assigned the default label.
- `valid_n`: valid model responses; `prediction_n`: all assigned predictions.
- `failed_n`: failed model classifications, including fallbacks.
- `accuracy_all`: exact assigned matches / all gold documents; unprocessed or unassigned records count as incorrect.

The default common scope is the intersection of assigned predictions across all completed, non-cancelled runs. The per-run scope includes each run's own assigned predictions. This makes fallback behavior part of evaluated classification performance while keeping model failure rates visible.

## Multiple seeds

In **Evaluations** or **Prediction**, enter seeds such as `11,22,33`. The UI starts with seed 9721; blank uses 9721. API callers may explicitly set query.seed to null for a server-selected seed. Duplicate and malformed seeds are rejected. The UI accepts JavaScript-safe integers; the API accepts signed 64-bit integers.

An evaluation with two models × two temperatures × three seeds creates **12 jobs**. A prediction with two tasks × three seeds creates **6 jobs**. Up to 100 distinct seeds, 50 base configurations/tasks and 500 expanded jobs per batch are supported. Check the expanded count before running costly experiments.

API example:

```json
{
  "name": "Seed comparison",
  "gold_id": "GOLD_ID",
  "task_id": "TASK_ID",
  "seeds": [11, 22, 33],
  "variants": [
    {"name": "Model A T=0.5", "profile_id": "PROFILE_ID", "query": {"model": "MODEL_ID", "temperature": 0.5}}
  ]
}
```

`seeds` also accepts a comma-separated string. Each evaluation variant may optionally provide its own `seeds` list. Precedence is variant seeds → evaluation seeds → `query.seed`. Prediction requests accept top-level seeds alongside the existing `task_ids`, dataset, connection, text column and query fields.

The concrete seed is saved in each job's query snapshot and sent to the provider. Prediction exports now include `seed` and retain one row per input × task × configuration × seed. Labels remain separate categorical assignments; TextLab does not average labels or silently take a majority vote.

## Means, standard deviations and error bars

Each run is scored independently. Reports group identical task revision, profile and query configurations that differ only by seed. Configuration names are not grouping keys; changing temperature, model, thinking, rationale or any other query/task setting creates a separate group.

Tables report arithmetic mean and **sample standard deviation (ddof=1)** across completed runs. Charts use those means with ±1 SD error bars, including per-class and runtime comparisons. These bars show observed between-run variation, not confidence intervals. Individual-run confusion matrices and predictions remain available for diagnosis.

Metrics with undefined values omit those values individually; `sample_n` gives each metric's actual denominator. SD is `null`/n/a with fewer than two defined observations. A zero SD means the available observations were equal. Completed-with-errors runs are included; cancelled/unfinished runs are excluded and counted in `excluded_runs`. They do not collapse the common scoring subset for completed runs.

Report JSON retains individual `runs` and adds aggregated `groups`, each with means, nested `std`, `sample_n`, seed lists, job IDs, `repeat_n` and `expected_runs`. CSV and HTML comparison tables show grouped statistics. Report ZIP additionally contains `individual_runs.csv`. Prediction runtime tables and manifest groups use the same aggregation; no classification-quality metrics exist without gold labels.

Changing a seed does not guarantee that a particular server/model will produce different outputs or be fully reproducible. Seed support and stochastic sampling depend on the backend, temperature and other settings.

## Upgrade

See UPGRADE.md for the schema 6→7 upgrade and preservation of existing snapshots.
