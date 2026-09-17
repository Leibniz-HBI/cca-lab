# Diagnostics

API and worker application logs go to stderr with timestamps, severity and module.
INFO (default) reports startup, CCA import outcomes, dataset imports, job start/completion,
and evaluation-report/prediction-export generation. Warnings identify rejected HTTP
requests and failed/fallback classification records.

Set TEXTLAB_LOG_LEVEL=DEBUG for request timing, dataset batch progress, job cursors,
LLM attempt numbers/error types, and individual result status/duration. Set the
variable for both processes and restart them. In Compose, edit .env and run
docker compose up -d --force-recreate, then docker compose logs -f api worker.
For direct Python runs, export TEXTLAB_LOG_LEVEL=DEBUG before starting each process;
Python does not automatically load .env.

Each API response includes X-Request-ID. CCA rejection messages include it for
matching browser errors to server logs. Browser developer tools show CCA picker,
upload-size and response events (enable Debug/Verbose console messages).
Import status/errors remain visible beside the import button after auto-refresh.

New diagnostic entries log IDs, counts, timings and error types rather than
codebook/document text, prompts, model responses, credentials or request bodies.
Detailed validation messages remain in the UI; existing per-job error logs retain
their usual diagnostic content. Unexpected internal errors retain stack traces.
DEBUG emits per-record information and should be switched back to INFO after diagnosis.

If no cca_import_started entry appears when selecting a file, inspect the browser
console and Network tab and hard-refresh to load the updated JavaScript.
