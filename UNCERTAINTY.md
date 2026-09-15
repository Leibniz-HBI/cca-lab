# Confidence, ambiguity and experiment size — TextLab 0.6

## Task settings

Two independent, default-off settings are available in **Define tasks**:

- **Self-reported confidence (uncalibrated)** requests a finite numeric `self_reported_confidence` between 0 and 1. The prompt defines it as estimated probability that the entire primary label set agrees with a competent adjudicator using the codebook. It is not a measured probability, codebook fit score, or fitted calibration model.
- **Structured alternative interpretations** requests up to five competing label sets under the same codebook. Each contains `labels`, `justification`, `supporting_quotes`, and `boundary_note`. Empty alternatives means the model identifies no genuine competing interpretation. Several labels inside one interpretation mean simultaneous multi-label coding; separate interpretations mean competing readings.

Example response with both options enabled:

```json
{
  "labels": ["FOR"],
  "self_reported_confidence": 0.65,
  "alternative_interpretations": [{
    "labels": ["AGAINST"],
    "justification": "The opposing view may be the author's own position.",
    "supporting_quotes": ["We should reconsider this policy."],
    "boundary_note": "The speaker attribution is unclear in the supplied excerpt."
  }]
}
```

The application validates label membership/cardinality, distinct alternative sets, nonempty explanations, and exact quote substrings. Alternative quotes may be empty when no explicit span supports the reading. Unknown fields, booleans/NaN/infinity as confidence, duplicate alternatives, and invented quotes invalidate the response and use the existing retry policy. Rationale and primary evidence remain independently configurable. Few-shot example confidence values are illustrative values attached to supplied codebook examples, not calibration observations.

Primary labels alone are scored by existing classification metrics. Alternatives do not silently convert a wrong primary decision into a correct one. Their substantive validity requires human review. No synthetic perspective/annotator identities are introduced.

Task snapshots preserve these settings. Editing a task affects new jobs only. Increase the output token budget when enabling richer responses; a truncated JSON response can fail validation. Existing task examples, prompt preview and JSON task import/export remain supported.

## Storage and downloads

Both fields are persisted in SQLite and exposed in job/evaluation result details and downloads. JSON/JSONL retains nested alternatives; CSV/Parquet serializes nested objects as JSON strings. Parquet confidence is numeric and nullable. Fallback, failed and unprocessed results have no confidence and no alternatives. For task settings that are off, confidence is null and alternatives are empty; consult the job snapshot to distinguish disabled output from an unambiguous result.

Prediction batches additionally persist `agreement.csv` and `agreement.jsonl` beside other filesystem exports. Evaluation report bundles include `agreement.csv`, `confidence.json`, `confidence_metrics.csv`, and SVG/PNG reliability and risk–coverage charts. HTML reports embed the confidence charts and metric table.

## Agreement across seeds

Open **Per-document agreement across seeds** in an evaluation or prediction detail. The paginated table and CSV/JSONL downloads include:

- Source dataset ID and row number, task and configuration identity, seeds.
- Number of eligible, valid, excluded, fallback and unprocessed outputs; cancelled and duplicate-seed runs are reported separately.
- Every tied modal label set, modal vote share, complete label-set counts and entropy in bits.
- Per-label selection frequencies, including labels never selected.

Groups match task identity/revision, resolved task settings, connection configuration, text column and all query parameters except seed. Different temperatures/models/tasks are not pooled. Cancelled runs are excluded as whole runs. Duplicate seed values in otherwise identical configurations contribute at most once (first completed run in experiment order). Only successful primary decisions count as votes; fallback labels never count. At least two successful distinct-seed runs are required for vote-share/entropy summaries; otherwise these fields are null. A single valid run still has descriptive label counts/frequencies.

Agreement is sampling stability, not probability of correctness, human agreement, or substantive ambiguity. Deterministic decoding can give identical outputs across seeds. Label-set entropy measures diversity of complete primary label sets, rather than clustering free-text explanations. Ties remain explicit; no arbitrary winner is chosen.

Agreement reads source documents in batches of 100 and queries indexed per-job result ranges, rather than loading the full prediction corpus into memory. CSV/JSONL exports cover all rows; the UI returns up to 50 rows per configuration per page. Agreement becomes available when all runs finish or are cancelled and is independent of the evaluation's gold scoring scope.

## Confidence diagnostics

The evaluation report adds:

- Binary Brier score for exact correctness of the whole predicted label set.
- Expected calibration error using ten fixed equal-width bins; confidence 1 belongs to the last bin.
- Error-detection AUROC and average precision, using `1 - confidence` as the error score. Both are unavailable when there is only one outcome class.
- Reliability plot: confidence versus observed exact-match accuracy.
- Risk–coverage plot: error rate among accepted decisions versus accepted fraction of valid scored outputs.

These diagnose self-reported scores; no learned calibration is fitted. Use held-out data for final assessment. Alternative interpretations are not scored against a single adjudicated gold label.

Confidence follows the selected assigned/common scoring subset, then excludes unsuccessful/fallback/missing-confidence outputs. Thus confidence coverage is conditional on valid scored outputs, not all source documents. Existing classification coverage/failure counts remain visible alongside it. Cancelled runs do not enter group averages. Metrics use per-run means and sample SD, not pooled pseudo-independent predictions. SD is unavailable for fewer than two contributing runs. Empty confidence bins are omitted from that bin's average and retain their contributing run count in report JSON.

Risk curves accept entire confidence ties; they never choose a favorable ordering within a tie. Individual curves are limited to 101 stored points. Group curves use 20 target coverage levels, select each run's first stored whole-tie point reaching the target, and plot mean achieved coverage and mean risk with sample SD. These are descriptive curves and error bars, not statistical confidence intervals. Undefined diagnostics appear as n/a.

## Query-count preview

Evaluation forms show **gold rows × added model/parameter configurations × seeds**. Model and temperature choices count only after **Add combinations**; the list of added configurations is authoritative. Prediction forms show **source rows × selected tasks × seeds × one model configuration**. Blank seeds means one run, using the query/server default. Concurrency changes throughput, not request count.

The preview also sums the maximum attempts including each configuration's retry limit. After creation, `query_count` in experiment details records the exact planned total, maximum attempts and run count derived from snapshots. API-created evaluations also honor per-variant seed lists. If a UI seed or override value is invalid, the estimate reports the error.

These counts are workload estimates, not time forecasts. Empty/rejected texts may make no request, cancellation reduces work, and model loading, context length, generated tokens and server batching affect runtime. Richer alternatives/confidence are requested in the same classification query, not a separate critic call. Actual requests and runtime remain tracked by the existing worker.

## Upgrade

Stop API and worker and back up the complete data volume, then install/rebuild and restart both with the same data location. Schema version 5 adds nullable confidence and an empty-default alternatives column. Historical outputs remain unchanged; old saved prediction artifacts are retained, and new batches include the new fields/files. Older report snapshots have no confidence diagnostics and display n/a; agreement can still be computed from their saved primary labels. Reload the browser. See UPGRADE.md.
