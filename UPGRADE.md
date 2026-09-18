# TextLab 0.10

From 0.9: replace the source, restart API and worker, and hard-refresh the browser.
No database migration or new Python dependency is needed. Codebooks and saved
results remain unchanged; the CCA schema is unchanged.

Existing 0.9 job snapshots retain their evidence-first-v1 compiler and validation
behavior. New jobs default to cca-reference-v2. Reusing an evaluated job for prediction
retains its prompt protocol. A paired comparison can explicitly select either
compiler through the query configuration; field order remains fixed in both.
See PROMPTS.md.

## Installations older than 0.9

This release changes the task API and stored task/snapshot representation to
{codebook, execution_defaults}. Legacy task migration is intentionally not provided.

Start with an empty TEXTLAB_DATA directory, or a new Docker Compose project/volume.
Keep any earlier installation and its data separate. Do not attach a 0.9 worker
to an earlier database containing tasks or snapshots in the old format.

Follow README.md for Docker or direct Python setup. Existing standards-compliant
CCA JSON files can be imported into the fresh task library. Configure execution
defaults after import. CCA files do not contain model connections or job settings.

The SQL layout remains schema version 6; the breaking change concerns JSON task
documents and API consumers. External clients must send the new task shape.
See CCA.md for a complete payload example. No new Python dependencies are required
relative to 0.8.1. Restart both processes after installing and hard-refresh the browser.
