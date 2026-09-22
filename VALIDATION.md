# Validation — CCA-Lab 0.13.1

126 Python tests passed, including concurrent endpoint scheduling, same-endpoint serialization, pause/cancel draining, and immutable evaluation snapshots across new evaluations and profile edits. Obsolete executor and migration tests were retired. Current coverage includes codebook-only task validation, rejection of unsupported protocols and database schemas without mutation, preview/execution consistency, batched and binary classification, context, retries, fallbacks, interruption budgets, thinking capture, cancellation, quality/runtime/confidence metrics, reports, exports, and deletion.

Regression checks in `tests/detail_races_unit.cjs` and `tests/model_selection_unit.cjs` cover delayed details/reports, connection switches, stale model lists and editor reopening. JavaScript checks passed for comma-separated parameter expansion, seeds and query estimates, and numeric/text metric sorting with missing values. Run `node tests/configurations_unit.cjs` and `node tests/tables_unit.cjs`. JavaScript syntax checks also passed.

The CCA-Lab wheel builds with the renamed Python package, current executor/compiler, schema and sortable-table assets. No old package namespace is bundled.

Both browser workflows passed using Playwright and Chromium against a disposable API/worker, including sortable metrics and sorting in standalone HTML reports. Browser checks use mocked model responses. `tests/experiments_browser.cjs` covers configuration defaults and expansion, query counts, previews, result-table sorting in both directions with keyboard activation and refresh retention, evaluation, binary prediction, request logs and mobile layout. `tests/cca_browser.cjs` covers CCA file selection/import/edit/export, field validation, gold editing, single-run reporting, error logs, prediction and standalone HTML report sorting. Use a fresh data directory for each workflow and set CCA_LAB_TEST_URL and optionally CCA_LAB_SCREENSHOT_DIR.

Three non-failing Python warnings concern test-client deprecations and a single-class scikit-learn metric fixture. Model calls are mocked. No live-model accuracy/calibration benchmark, GPU throughput benchmark or new 500 MB import benchmark was performed. Docker itself was not run in this environment.

Run the Python suite with `python -m pytest -q`. Use requirements.lock for reproducible dependencies.
