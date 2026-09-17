# CCA Schema 0.1 interchange — TextLab 0.8

## Import

Open **Define tasks → Import CCA codebook JSON**, select a UTF-8 JSON file, and review the new task. UTF-8 BOM is accepted. Every import creates a new task; it never overwrites a task with a matching codebook ID. The task is saved immediately, and the editor opens for review.

`POST /api/tasks/import-cca` accepts the raw codebook JSON with `Content-Type: application/json` (maximum 5 MiB). It returns the new task ID with HTTP 201. HTTP 422 reports invalid JSON, duplicate JSON keys, schema violations, duplicate category IDs, unknown example labels, or TextLab application limits. No partial task is created on failure.

Validation uses the exact supplied CCA 0.1 schema bundled at `textlab/schemas/cca-schema-0.1.schema.json`, including date/URI formats. Codebook `$schema` identifiers are retained as provided; no remote schema is fetched. This endpoint always validates against bundled CCA 0.1, not arbitrary schemas named by the document.

## Mapping

| CCA field | TextLab behavior |
|---|---|
| `title`, `description` | Task name and description |
| `task.instructions` | General coding instructions |
| `task.unit_of_analysis`, `task.context` | Dedicated task fields, included in prompts |
| `classification_mode` | Single-label or multi-label mode |
| Category `id` | Machine-facing output label and gold-label identifier |
| Category `label` | Human-facing display name included in the prompt |
| Category definition, inclusion/exclusion criteria, coding notes, aliases | Preserved as structured category fields and included in prompts |
| Example text and labels | Few-shot example using category IDs |
| Example explanation | Example rationale |
| Example context | Separate context field in the example's user message |
| Identity, version, authors, maintainers, dates, language, references | Preserved in CCA source metadata and exported |

The task editor's main **Label** input remains the machine-facing ID. Open **Category name, criteria and notes** to edit the display name and structured criteria. Open **CCA codebook context and provenance** to edit units, permitted context, and imported identity/provenance metadata. Additional few-shot examples are edited as JSON; their `context` property is retained.

Task context describes which contextual information may be used. It does not automatically retrieve additional dataset columns or preceding documents; include needed context in the selected input text. Example context is explicitly supplied with that example. The evidence-first protocol still requires quoted evidence to occur in the classified text itself.

Imports accept a one-category codebook, as permitted by CCA. Existing application bounds still apply (e.g. up to 200 categories/examples, 100 characters per output ID, 200 characters for task titles); schema-valid documents exceeding those limits are rejected explicitly instead of truncated. Whitespace normalization follows existing TextLab task validation; this is a semantic JSON interchange, not a byte-for-byte file archive.

## Export

Each task card offers **CCA JSON ↓** alongside native **JSON ↓**. `GET /api/tasks/{id}/export-cca` produces a validated CCA 0.1 codebook as an attachment.

Export is rebuilt from current editable task fields, with preserved source identity/provenance. Editing a definition, category ID, criterion, context or example therefore updates the exported codebook. Imported optional metadata and optional empty `examples: []` are preserved. TextLab's internal revision counter is separate from the codebook's semantic version; update the CCA version and modified date in the provenance editor when appropriate.

For a native task without imported metadata:

- A stable ID `urn:textlab:task:<task ID>` is generated.
- Codebook version is `0.1.<TextLab revision minus one>`.
- Unit of analysis defaults to `document` and is editable.
- Missing task description falls back to the task's actual instructions.
- Human category names fall back to their existing output labels.
- The ambiguity rule is appended to general coding instructions, so it is not lost on re-import.
- Category-specific few-shot examples are converted to standard top-level examples.

CCA is a codebook interchange format. Model connections, seeds, thinking levels, output switches, fallback behavior and runtime settings are not CCA fields and are not exported. Use native Task JSON when those settings must be retained. Import uses normal TextLab defaults for them; it does not launch any jobs.

CCA 0.1 cannot represent empty label assignments. Export of a task with **Allow empty selection** enabled is rejected with a clear error; it is not silently converted to a different coding policy.

## Reproducibility and upgrade

Imported content is part of the task specification and immutable job snapshots, including criteria, context and CCA metadata. Existing jobs and reports retain their saved task specifications. Native task JSON remains supported.

Install the updated requirements or rebuild the containers to include JSON Schema validation dependencies. Restart API and worker and reload the browser. Database schema remains version 6: new fields are stored in the existing task/snapshot JSON. The attached standard itself is bundled unchanged.
