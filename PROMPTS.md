# Prompt compilation

Experiments use cca-reference-v2. The order of enabled output fields remains
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

## Protocol provenance

cca-reference-v2 is the only supported compiler. Its identifier is recorded in snapshots and attempt logs. The query metadata field accepts only this fixed value; it is not a selectable compiler. Current saved snapshots remain readable without rewriting them.

Prompt formatting is tested for implementation correctness; no empirical accuracy or calibration gain is claimed.
