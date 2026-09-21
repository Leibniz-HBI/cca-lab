# Evaluation in TextLab

Evaluations support repeated seeds, grouped mean/SD tables, error-bar charts and explicitly scored fallback labels. [REPETITIONS.md](REPETITIONS.md) defines the updated scoring and repetition conventions.

## Workflow

1. Open **Gold datasets → Upload CSV** and wait for import.
2. Choose **Map columns**. Map document ID, text, gold label and optional context; defaults are `doc_id`, `text`, `gold_label`.
3. Select single-label or multi-label mode. Multi-label cells split on a literal separator, default `|`. Empty label sets require explicit permission. Document IDs must be unique and nonempty after trimming, and texts nonempty. Labels are case-sensitive; empty components and duplicates are invalid.
4. Open **Evaluations → New evaluation** and select the task and registered gold dataset.
5. Choose connection, models, parameter values and Off/On/Compare both switches. **Generate configurations** creates the Cartesian product; review each configuration. Repeat with other connections if needed.
6. Choose seeds, joint/binary strategy, batch size, context, output fields and execution settings in the same configuration builder. Inspect the query estimate and actual-data prompt preview. See EXPERIMENTS.md.
7. Start the evaluation. Each configuration becomes a persistent job; variants run sequentially with their configured request concurrency.
8. Choose **Compare** to inspect quality, runtime, class metrics, confusion matrices, predictions and downloads. Pause/resume/cancel applies to eligible child runs. Each child also has an individual result view.

Gold/task modes and label cardinalities are validated before any jobs are created. Single-label tasks require exactly one category ID. Multi-label tasks accept an empty set when no category applies; enable empty cells in the gold registration to use blank gold assignments. Gold labels are not added to prompts. Keep manually authored few-shot examples separate from evaluation examples to avoid leakage.

Gold registrations preserve normalized labels and column mappings. Use Edit to change the name, source dataset, column mappings, label mode, separator or empty-cell policy. Unused registrations update in place; registrations referenced by evaluations are saved as new revisions, leaving existing evaluations and their gold data unchanged. Invalid edits roll back atomically. Default maximum: 50,000 gold rows (`TEXTLAB_MAX_EVAL_ROWS`) and 50 base configurations and 500 expanded runs per evaluation. Metric computation retains gold/prediction labels in memory, so increasing these limits increases memory requirements.

## Quality metrics

Two scoring scopes are available:

| Scope | Documents scored |
|---|---|
| Common valid documents (default) | Identical intersection of assigned predictions from completed, non-cancelled runs |
| Valid documents per variant | Each variant's own assigned subset (including fallbacks), which may differ in difficulty |

Coverage always uses all gold documents: valid predictions / total gold documents. Accuracy (all) scores fallback labels as assigned output; unassigned or unprocessed records count as incorrect. Failed multi-label predictions are not treated as empty label sets.

| Metric | Single-label | Multi-label |
|---|---|---|
| Accuracy | Correct class fraction | Exact-match/subset accuracy |
| Precision, recall, F1 | Per class; macro, micro, weighted | Same, plus sample average |
| Cohen's kappa | Multiclass and binary per class | Binary per class; macro mean of defined class kappas |
| Matthews coefficient | Multiclass and binary per class | Binary per class; macro mean |
| Hamming loss | Class error fraction | Fraction of incorrect label indicators |
| Jaccard | Where included in report | Sample-average label-set similarity |

Macro includes every task class, including classes without gold support. Weighted uses gold support in the selected subset. Micro pools TP/FP/FN. Precision/recall/F1 with a zero denominator are 0; undefined kappa is null; zero-denominator MCC is 0, following scikit-learn. No valid documents yields null/n/a metrics. Multi-label macro kappa/MCC are not global multiclass coefficients.

Rationale, evidence and thinking are not scored for semantic quality. Validation failures in requested output fields invalidate the entire response and therefore affect coverage.

## Runtime comparison

Quality and runtime appear together in the report, model comparison tables and chart metric selector. Runtime always covers the whole variant, independent of scoring scope.

| Field | Meaning |
|---|---|
| `active_seconds` | Sum of timed processing batches, including retries and client overhead, excluding pauses and waiting between batches |
| `elapsed_seconds` | First start to finish, including pauses |
| `documents_per_second` | Processed records / active seconds |
| `successful_documents_per_second` | Valid records / active seconds |
| `mean_document_seconds` | Allocated request duration including retries / processed records |
| `completion_tokens_per_second` | Reported output tokens / active seconds; unavailable token counts contribute 0 |
| `timing_complete` | Whether the full active measurement is available |

Per-document times allocate shared batch duration equally; they overlap with parallel requests and must not be summed as job wall time. No-work rates appear as n/a. Legacy jobs and uncleanly interrupted timing cannot provide reliable active/elapsed comparisons. Model startup, caching, API network overhead, context lengths, output budgets and concurrency can affect timings. TextLab reports observed application runtime, not isolated GPU inference time.

## Saved outputs and reports

After all variants finish or cancellation drains, the worker saves reports for both scoring scopes. Failed report generation can be retried. Reports support JSON, metrics CSV, per-class CSV, standalone HTML and ZIP. The ZIP includes quality and active-runtime charts, class charts, per-variant confusion matrices and gold/prediction CSV. Charts can also be downloaded individually as SVG or PNG.

The UI exposes macro/micro/weighted/sample quality summaries, per-class tables, confusion views and a paginated prediction viewer. Class charts show up to 40 classes; tables and CSV contain all classes. Gold/prediction exports include unprocessed rows and are available as CSV/JSONL. CSV formula escaping is applied; JSONL retains raw strings.

Prediction rows retain rationale, validated evidence with character offsets, returned thinking, raw response, attempts, errors and timings. Thinking returned on retries remains in `attempt_outputs`; hidden server-internal reasoning is not accessible. See README for task thinking controls and provider mapping.

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/gold-sets` | Register imported dataset with column mapping |
| `GET /api/gold-sets[/{id}/preview]` | List / preview normalized gold records |
| `POST /api/evaluations` | Start task + gold dataset + variant configurations |
| `GET /api/evaluations[/{id}]` | Progress, snapshots and runtime |
| `POST /api/evaluations/{id}/{pause,resume,cancel}` | Control eligible variants |
| `POST /api/evaluations/{id}/retry-report` | Retry failed report calculation |
| `GET /api/evaluations/{id}/report` | `scope=common|valid`, `format=json|csv|class_csv|html|zip` |
| `GET /api/evaluations/{id}/chart` | `kind=overview|classes|confusion`, `metric`, `scope`, `job_id`, `format=svg|png` |
| `GET /api/evaluations/{id}/predictions` | Paginated variant predictions |
| `GET /api/evaluations/{id}/export-predictions` | CSV/JSONL over all variants |
| `DELETE /api/evaluations/{id}` | Delete completed evaluation and its child runs/results |
| `DELETE /api/gold-sets/{id}?cascade=true` | Delete registration and dependent completed evaluations |
| `POST /api/predictions` | Run one dataset through `task_ids` using the selected model/query |
| `GET /api/predictions[/{id}]` | Prediction batch status, runs, runtime and saved files |
| `POST /api/predictions/{id}/{pause,resume,cancel,retry-export}` | Control batch / retry failed export |
| `GET /api/predictions/{id}/download/{format}` | Persistent CSV/JSON/JSONL/Parquet/manifest |
| `DELETE /api/predictions/{id}` | Delete completed batch, child runs and files |

Interactive request schemas are at `/docs`. There is no automatic hyperparameter optimization, cross-validation or confidence interval estimation. Add seeds as explicit variants for repeated runs.

Single-run configurations display metric values without standard deviations or error bars. Repeated configurations retain means and sample SD. Raw report JSON retains the aggregate statistics.

PUT /api/gold-sets/{id} accepts the same fields as registration and returns {id, revised_from}. A revised_from value indicates that a new registration was saved to preserve prior evaluations.
