# CCA Schema 0.1 reference implementation

The uploaded CCA Schema 0.1 JSON Schema is bundled unchanged at
textlab/schemas/cca-schema-0.1.schema.json. It is the validation authority.
No remote schema retrieval occurs. TextLab supplements Draft 2020-12 validation
with the category-ID uniqueness and example-reference checks required by the standard.

## Authoritative representation

Every task is stored, returned by the task API and embedded in immutable job
snapshots in this shape:

```json
{
  "codebook": {
    "$schema": "https://cca-schema.org/schema/0.1/schema.json",
    "id": "sentiment-study",
    "version": "0.1.0",
    "title": "Sentiment",
    "description": "Evaluative orientation of a document.",
    "task": {
      "instructions": "Assign the category that best describes the evaluative orientation.",
      "unit_of_analysis": "document",
      "classification_mode": "single_label",
      "categories": [
        {"id": "POS", "label": "Positive", "definition": "Expresses a favorable evaluation."},
        {"id": "OTHER", "label": "Other", "definition": "Does not express a favorable evaluation."}
      ]
    },
    "examples": [
      {"text": "Excellent!", "labels": ["POS"], "explanation": "Explicit positive evaluation."}
    ]
  },
  "execution_defaults": {
    "rationale": false,
    "evidence": false,
    "alternatives": false,
    "confidence": false,
    "thinking": "default",
    "default_label": null
  }
}
```

There is no separate original-source copy or parallel editable task definition.
Runtime accessors read the codebook directly. Standard category names and criteria
appear in prompts, but outputs, gold assignments, evidence labels, fallbacks and
metrics reference category IDs.

## Editor

The editor starts with a blank title, description, instructions and one blank
category. It generates a UUID codebook ID, version 0.1.0 and unit "document".
Complete required fields before saving.

- Codebook identity: title, description, ID, version; optional language, authors,
  maintainers, created/modified dates, citation/DOI references.
- Coding instructions: instructions, unit, single-label/multi-label, permitted context.
- Categories: ID, label, definition; expandable inclusion/exclusion criteria,
  aliases and coding notes. Inclusion/exclusion criteria use two multiline bullet editors; aliases use individual text controls.
- Examples: text, category-ID selection, optional context and explanation.
  One list supports both single-label and multi-label examples.
- TextLab execution defaults: optional output fields, thinking and fallback category.
- Prompt preview: collapsed independently, generated from current unsaved values.

No ambiguity_rule exists. Put such decisions in instructions or coding_notes.
Multi-label tasks accept zero or more category IDs: [] means no category applies. Single-label tasks require exactly one ID. Gold registrations must enable empty gold cells to interpret blank cells as []. No task-level switch or schema change is needed.

Saving, importing and prompt preview all run the same schema validation.
Errors carry JSON pointers and appear beside affected editor fields.
Changing or removing a referenced category leaves missing IDs visible for correction;
it does not silently reassign example or fallback labels.

Codebook version and dates are researcher-controlled. Saving increments only
the internal TextLab revision. Editing an evaluated instrument as a copy creates
a new codebook ID.

## Interchange and API

- POST /api/tasks: accepts {codebook, execution_defaults}; defaults are optional.
- PUT /api/tasks/{id}?revision=N: same representation, optimistic revision check.
- POST /api/tasks/preview: same representation; validates and generates messages.
- POST /api/tasks/import-cca: accepts a bare CCA JSON codebook, creating a new task
  with default execution settings.
- GET /api/tasks/{id}/export-cca: exports exactly the current codebook.
- "CCA JSON ↓" downloads only the standard codebook.
- "TextLab task JSON ↓" downloads both codebook and execution defaults.

CCA import accepts UTF-8/BOM, rejects duplicate keys and limits uploads to 5 MiB.
Schema-allowed values are not trimmed, renamed or silently truncated.
The former limits of 200 categories/examples and 100-character category IDs no
longer apply to codebooks. Model context limits and normal job/data resource limits
remain separate execution constraints.

An unedited import/export preserves the JSON data, including optional metadata
and empty examples/references arrays; serialization whitespace/key ordering may differ.
The editor preserves these optional arrays if originally present.

## Prompt and runtime semantics

A category ID is distinct from its human-facing label and aliases.
Inclusion/exclusion criteria and notes are included explicitly in the prompt.
Reference examples preserve supplied text, labels, explanation and context; no missing output annotations are synthesized. Task context describes how
context may be used; it does not automatically retrieve neighboring documents.

The examples_per_category query parameter now applies to the one CCA examples
list. Examples are considered in codebook order. An example is included only when
all its IDs are below the cap; a multi-label example is emitted once and counts
towards every assigned ID. Zero disables all few-shot examples.

Query overrides modify only a snapshot's execution defaults, never the codebook
or the saved task. The enabled-field output order is unchanged; new prompts use cca-reference-v2. See PROMPTS.md.

## Bundled examples

examples/task.cca.json and task_multi.cca.json can be imported in the UI.
The corresponding task.json/task_multi.json files are native API payloads.
The multi-label example and its gold CSV use an explicit NONE category.
