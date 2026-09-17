# Confidence, ambiguity and experiment size — TextLab 0.7

## Fixed evidence-first generation

All newly generated prompts use this fixed order, without an order setting:

1. `evidence`
2. `candidate_interpretations`
3. `rationale`
4. `labels`
5. `self_reported_confidence`

Existing switches for evidence, candidate comparison (`alternatives` in task JSON), rationale and confidence remain independent. Disabled fields are omitted; the relative order of enabled fields never changes. The schema properties, required-field list, prompt instructions, few-shot examples and demo responses all use this order.

Evidence entries associate an exact input quote with **any category in the codebook**, including categories not selected in the final decision. The prompt requests relevant supporting and conflicting signals before choosing a label. Quotes still require exact substring validation and receive character offsets. An unknown label or invented quote is rejected. Empty evidence is allowed when the decision concerns absent evidence.

When candidate comparison is enabled, the LLM returns **one to six distinct complete label sets**, including the eventual primary interpretation. Each candidate has `labels`, `justification`, `supporting_quotes` and `boundary_note`. A single candidate represents an unambiguous reading. Multiple labels within one candidate apply simultaneously; multiple candidates represent competing readings under the same codebook. Candidate quotes must be exact input substrings and may be empty where evidence is absent. The boundary note can explicitly state that no material counter-evidence was identified; the prompt does not require inventing objections.

The rationale briefly compares the plausible interpretations and identifies decisive inclusion, exclusion or priority rules. The final `labels` must match one complete candidate set (order-insensitive), not a union of competing candidates. TextLab derives `alternative_interpretations` by removing that primary set from the candidate list; the model must not emit this derived field. Duplicate candidates, a missing primary candidate, invalid label cardinality, and extra fields are validation errors and use the existing retry policy.

Example model response with all options enabled:

```json
{
  "evidence": [
    {"label": "FOR", "quote": "We support the policy."},
    {"label": "AGAINST", "quote": "But its costs are unacceptable."}
  ],
  "candidate_interpretations": [
    {
      "labels": ["FOR"],
      "justification": "The speaker explicitly supports the policy.",
      "supporting_quotes": ["We support the policy."],
      "boundary_note": "The following cost criticism limits the strength of support."
    },
    {
      "labels": ["AGAINST"],
      "justification": "The cost criticism could imply rejection.",
      "supporting_quotes": ["But its costs are unacceptable."],
      "boundary_note": "The speaker nevertheless explicitly endorses the policy."
    }
  ],
  "rationale": "Under this codebook, explicit endorsement takes priority over criticism of implementation costs.",
  "labels": ["FOR"],
  "self_reported_confidence": 0.75
}
```

Here the stored alternatives contain only the AGAINST candidate. Both full candidates are retained separately. The example assumes that the supplied codebook actually specifies that priority rule.

Self-reported confidence is a finite number between 0 and 1, estimating exact agreement with a competent adjudicator. It remains **uncalibrated**, not a codebook-fit or prototypicality score. Few-shot confidence values attached to supplied codebook examples are illustrative, not calibration observations. Primary labels alone enter classification metrics; plausible alternatives do not silently make a wrong primary decision correct.

JSON object order is not a semantic JSON constraint. TextLab requests the fixed generation sequence everywhere but does not reject an otherwise valid response solely because a provider returns its properties in another order, or pretend that reserializing a completed answer changes generation. Raw responses are preserved for auditing actual order. Backend compliance and quality gains require testing with the selected model; this release does not establish better classification performance.

New job snapshots and inference attempt logs identify the fixed protocol as `evidence-first-v1`. It is not a task/query option. Increase maximum output tokens when using rich candidates and evidence. No extra LLM calls are added, so query-count estimates are unchanged.

## Storage and downloads

Candidate interpretations, derived alternatives and confidence are persisted in SQLite and exposed in job/evaluation result details and downloads. JSON/JSONL retains nested alternatives; CSV/Parquet serializes nested objects as JSON strings. Parquet confidence is numeric and nullable. Fallback, failed and unprocessed results have no confidence, candidates or alternatives. For task settings that are off, confidence is null and alternatives are empty; consult the job snapshot to distinguish disabled output from an unambiguous result.

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

Stop API and worker and back up the complete data volume, then install/rebuild and restart both with the same data location. Schema version 6 adds an empty-default candidate column to the existing confidence/alternatives fields. Historical outputs remain unchanged; old saved prediction artifacts are retained, and new batches include the new fields/files. Older report snapshots have no confidence diagnostics and display n/a; agreement can still be computed from their saved primary labels. Reload the browser. See UPGRADE.md.

Historical alternatives remain untouched; they are not retroactively reconstructed into candidate lists. Old completed results therefore have empty candidates. Finish existing jobs using the old worker before upgrading when consistent inference protocols within an experiment are required. Resuming old jobs with the new worker uses the new fixed protocol for new requests; attempt logs identify it. Reusing an older evaluated configuration also uses the new generation protocol, so repeat evaluation before treating its quality as equivalent.
