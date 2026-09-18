# Validation

108 Python tests passed. Coverage includes CCA validation, prompt/request consistency for both providers and all output modes, retries and fallbacks, error logs, repeated evaluations, confidence and agreement, runtime, reports, exports and deletion.

Startup tests cover concurrent fresh initialization, repeated startup without data changes, and rejection of unsupported versions, missing columns, indexes and tables without altering data. Worker interruption recovery remains tested. A database populated with completed prediction jobs and saved exports before cleanup reopened with an identical SQL dump after cleanup.

The Playwright/Chromium workflow passed task creation and field errors, real CCA file selection across background refresh, persistent invalid-file feedback, import/edit/export, multiline criteria, prompt preview, evaluation, prediction and downloads, with no JavaScript or HTTP 5xx errors.

Three non-failing warnings concern test-client deprecations and a single-class scikit-learn metric fixture. No live-model accuracy benchmark, GPU throughput benchmark or new large-corpus test was performed.

Run Python checks with python -m pytest -q. The optional tests/cca_browser.cjs browser test requires Playwright, Chromium and a disposable running API/worker. Use the pinned requirements.lock for reproducible dependencies.
