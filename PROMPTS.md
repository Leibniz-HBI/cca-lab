# Prompt compilation — TextLab 0.10

New experiments use cca-reference-v2. The order of enabled output fields remains
evidence → candidate_interpretations → rationale → labels → self_reported_confidence.

## Prompt structure

Classification task (title, description, unit, assignment cardinality), coding
instructions, optional context policy, categories, selected reference examples,
and response requirements. Category criteria render as bullets. Authored
instructions and criterion text are preserved; the compiler does not infer
priority or AND/OR rules. Administrative metadata is excluded.

Reference examples contain only their supplied CCA fields. They are clearly
identified as annotated reference data in the system message, not synthesized
assistant outputs. No confidence, evidence spans, candidates or boundary claims
are inferred from labels. The separate mock provider still generates synthetic
outputs for plumbing tests.

Each enabled output field is explained once. Boundary notes may be empty strings
when no material concern exists; null/missing fields remain invalid. Evidence
instructions request shortest sufficient exact spans and relevant counter-evidence.

With native json_schema, the full schema is passed through OpenAI response_format
or Ollama format, not duplicated inside the prompt. json_object and none modes
include an explicit schema in the prompt. Local result validation runs in every mode.

## Criteria editing

Inclusion and exclusion criteria each have one multiline field.
Write "- " before each criterion; indent continuation lines with two spaces.
Plain text without an initial "- " is a single criterion; an empty field removes
the optional property. Example:

    - Explicit positive evaluation.
      Consider the complete utterance.
    - Positive meaning after resolving negation.

Indent embedded bullet lines too. The parser removes only the format's two-space
continuation prefix. Unedited imported values are retained exactly, including
original line endings; editing uses browser-normalized newlines.
CCA arrays and the bundled CCA 0.1 schema remain unchanged.

## Preview

The collapsed Prompt preview section allows selection of provider and output mode.
It displays decoded system/user messages and expandable raw request JSON.
The preview and worker share request construction. It uses model "preview",
placeholder text and displayed preview settings; it does not call an LLM.
It contains no authentication headers or credentials.

POST /api/tasks/preview still returns messages.
POST /api/tasks/preview-request accepts {task, query?, provider?, text?} and returns
{prompt_protocol, path, request, note}. Provider is openai or ollama.

## Paired evaluation

scripts/compare_prompts.py takes an ordinary evaluation request JSON with an
existing task ID, held-out gold ID, variants and seeds. It duplicates each variant
for evidence-first-v1 and cca-reference-v2, preserving other parameters.

    python scripts/compare_prompts.py evaluation.json
    python scripts/compare_prompts.py evaluation.json --start --api http://127.0.0.1:8080

Without --start it only prints the request. --start creates and runs an evaluation,
which consumes model queries. Up to 25 base configurations expand to 50 variants;
normal total-run limits still apply. Query count includes both protocols.

Use the same held-out data, task, models, parameter configurations and seeds.
Enable confidence on the task before starting if confidence diagnostics are needed.
Compare classification metrics and coverage, confidence diagnostics, runtime,
and token usage. Error-log exports distinguish validation failures, recovered retries,
transport errors and terminal failures; terminal failure rate alone is not an
invalid-response rate. Count validation-failed attempts / all attempts separately
when assessing output validity. Record warm-up/model-loading/order effects when
interpreting runtime; the worker executes variants sequentially.

Protocol IDs are stored in job snapshots and attempt logs and separate seed
aggregation groups. Existing evaluation tables, confidence plots and export bundles
support the paired variants. Historical 0.9 jobs retain the old compiler; no old
results or codebooks are rewritten.

No empirical accuracy or calibration improvement is claimed by this release.
The test suite and mock-provider browser check verify implementation behavior,
not model quality. Run the paired evaluation on your models before adopting the
new prompt for a substantive study.
