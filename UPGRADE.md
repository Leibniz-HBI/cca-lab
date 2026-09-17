# TextLab 0.9 — fresh installation

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
