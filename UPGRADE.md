# Updating CCA-Lab 0.13.0 → 0.13.1

Stop the API and worker gracefully, replace the application files (or rebuild the Docker image), then restart both using the same data directory/volume. Hard-refresh the browser. No database migration or fresh setup is needed: schema 7, job snapshots, requests and results are preserved. Queued jobs on independent endpoints become eligible automatically.

This patch does not relabel historical snapshots: a model name stored at job creation remains the authoritative requested model. If an existing evaluation still shows an unexpected model, inspect its individual-run snapshot and LLM request log before interpreting its results.

## Earlier installation boundary (0.13.0)

CCA-Lab 0.13.0 uses the Python package `cca_lab`, distribution `cca-lab`, environment variables `CCA_LAB_*`, database file `cca_lab.sqlite`, Docker image `cca-lab:local` and volume `cca-lab-data`.

The 0.13.0 release intentionally removes earlier-version compatibility. It does not upgrade earlier schemas, translate saved jobs, recognize old environment-variable aliases or load the former database filename. Use a fresh CCA-Lab data directory/volume. Keep any previous installation and its data separately if you need its historical results. Standard CCA codebooks can be exported and imported normally; datasets can be uploaded again.

Startup creates the current schema (7) atomically or validates an existing current CCA-Lab database. Unsupported schemas are rejected without modification. Subsequent same-version restarts preserve current tasks, jobs and exports. Both API and worker must use the same CCA_LAB_DATA directory.

Current crash recovery remains: committed category/document decisions are retained, interrupted requests consume an attempt and record their unknown outcome, incomplete timing is flagged, and interrupted export builds return to pending. Pause/resume/cancel behavior is unchanged.

Follow README.md for Docker or Python startup. Stop the previous API/worker before binding the same port. Hard-refresh the browser after starting CCA-Lab.
