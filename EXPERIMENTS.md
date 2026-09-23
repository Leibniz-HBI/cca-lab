# Experiment configurations 

Tasks describe CCA codebooks only. Evaluation and prediction share the same configuration builder: choose models, generate combinations, review the table and query estimate, inspect a prompt preview, then start. Defaults are maximum output tokens 8192, retries 3 and seed 9721.

## Variations

Boolean options offer Off, On and Compare both. Numeric and enumerated parameters accept comma-separated values. Seeds use commas and repeat each configuration; they are not averaged within an individual prediction. The generated configuration table is authoritative. Editing builder controls does not change already generated configurations until Generate is selected. Each option has a hover/focus explanation. Limits: 50 configurations, 100 seeds, 500 expanded jobs.

Configurations include sampling, thinking, output fields, few-shot limits, strategy, batch size, context, concurrency, retry budget, input limits, structured output and fallback category. Additional provider parameters accept JSON. Invalid settings or unavailable category IDs are rejected before jobs are inserted. Binary strategy requires all selected tasks to be multi-label. A shared fallback ID must exist in every selected task.

## Context

Gold registration optionally maps a context column, distinct from document ID, text and gold. Prediction maps context directly from the selected dataset. Including context is a separate per-configuration switch; mapping alone does not include it. In each sample, context precedes the target text. Empty context cells are allowed. Context and text have separate limits and share the selected reject/truncate policy. Gold labels are never sent to the model. Evidence quotes and candidate supporting quotes are validated against target text only.

## Joint and binary classification

Joint mode presents the complete codebook and returns one label set per document. Binary mode presents one category definition per query, asking whether it applies: [category_id] or []. Selected few-shot examples are projected into positive/negative examples for that category; their explanations are omitted to avoid leaking competing category definitions.

Binary category decisions are independently validated and persisted. After every category has a terminal outcome, successful labels are combined in codebook order. Evidence is combined, rationales carry category identifiers, and candidates/alternatives retain their category provenance. Each result includes component_results with complete per-category decisions and request IDs. A failed category is not treated as a negative answer: the entire document is failed, or explicitly assigned the configured fallback. Rejected inputs that never reached the model do not receive fallback labels.

Self-reported confidence concerns one joint label set or one binary decision. Binary scores are retained and evaluated per category; no unsupported whole-set confidence is manufactured. Reports include per-category confidence metrics and confidence plots. Quality metrics and agreement use the final aggregated document label set.

## Batching and retries

Each request contains up to batch_size samples, bounded by a serialized input character budget. Batches split deterministically within bounded worker windows. Reference examples are also grouped into paired user/assistant batches. They contain supplied annotations only, not invented evidence or confidence. The output budget applies to the entire request, including every result and any server-counted thinking tokens.

The response is {"results":[{"id":"1","labels":["A"]}, ...]}, with enabled fields following the fixed evidence → candidates → rationale → labels → confidence order. IDs must match input samples. Missing/duplicate IDs or invalid item fields retry the affected items; malformed envelopes and unknown IDs invalidate the envelope. Already valid items are retained and omitted from retries. Retries are additional attempts per unresolved document/category decision. HTTP 408, 429 and 5xx may retry; other HTTP errors terminate those decisions.

Pausing stops new requests and drains in-flight calls. Resume preserves completed components and original grouping. An interrupted reserved request consumes an attempt because the server may have processed it. Durable local accounting cannot guarantee exactly-once execution on the remote model server.

## Counts and runtime

For each task/configuration/seed run, nominal requests are ceil(document_count / batch_size), multiplied by category count for binary mode. Summing those values gives the planned count. Character splits, invalid inputs, cancellation and retries affect actual requests. A conservative ceiling is document_count × category_factor × (retries + 1), summed over runs.

Requests, input/output tokens and request duration are recorded once per API attempt. Document duration is an equal allocation of request duration across included samples, summed across category decisions and retries; it is not an isolated inference latency. Per-document token fields remain zero because exact per-item usage is unavailable. Use request logs and job totals for token analysis. Interrupted requests have unknown remote usage. Active/elapsed job time and document throughput remain available for performance comparisons.

## Logs, exports and reproducibility

Job details expose paginated LLM request logs and a streaming requests.jsonl download, including the effective request, batch membership, category, raw response, returned thinking, usage, duration and item errors. Headers and API keys are not saved. These logs contain source text; handle them with the same care as the dataset.

Prediction exports preserve one row per document × task × configuration × seed, including component_results. requests.jsonl stores shared responses without duplicating them into every document. Evaluation report ZIPs include request logs and configuration metadata alongside quality, runtime and confidence tables. CSV, JSON, JSONL and Parquet retain the same aggregated classification representation.

Batch size can affect model behavior and is part of the experimental configuration. Separate seed runs are summarized with means and sample standard deviations; one-run groups omit SD display and error bars. No empirical accuracy gain, calibration guarantee or throughput improvement is asserted. Validate the chosen model and configuration on representative gold data.

## Prompt compiler (0.14.0)

The selector next to Manual model IDs offers **User/assistant roles**, **Single system message**, and **Compare both**. The default remains User/assistant roles. Compare both expands the configuration product by two; each compiler has its own seed runs, request estimate and metric group. Configuration names and saved query snapshots identify the compiler (`roles` or `system`). Editing, duplication and reuse for prediction preserve this setting.

User/assistant roles uses batched example dialogue turns. Single system message places the same selected examples in an Annotated reference examples section of the system message, with only supplied labels, optional context and annotations. Missing evidence is not represented as an empty evidence finding. Both modes retain the final user message containing target samples and use the same output schema, validation, retries and aggregation. Binary mode still shows only the selected category and its positive/negative reference assignments. No codebook schema change is needed.

## Readable requests and JSON

Prompt previews, request logs, snapshots and JSON result/error details share a viewer. Readable mode displays structured fields and decoded string line breaks; JSON strings nested inside messages/responses are expanded for reading. Check **JSON mode** for syntax-highlighted, valid JSON, including the escapes needed for exact string representation. The viewer does not alter saved requests, responses or downloads and escapes HTML in source text. It is read-only; JSON editing fields remain plain editable JSON.

## Automatic output-budget retries (0.14.2)

If a response fails and the server reports a length stop (or token usage reaches the output budget), the next attempt doubles the current maximum output tokens. A thinking-only empty response without finish metadata is also treated as suspected exhaustion. Empty responses without such evidence receive an explicit missing-content error and ordinary retries. An already valid response is accepted even if the server reports a length stop.

The configured maximum is the initial budget. Increases apply to unresolved document/category decisions; a retry batch uses the largest required budget among its items. Further truncations double it again; other failures retain the current budget. Retries remain bounded by the configured retry count, and provider context/output limits still apply. Every actual request records its token budget; output logs retain finish reasons and exhaustion flags. Pending budgets survive pause/restart, while the original job configuration remains unchanged.
