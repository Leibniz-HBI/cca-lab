# Validation — CCA-Lab 0.15.0

164 Python tests passed. Access-control coverage includes real credential login, CSRF and origin rejection, session revocation, role enforcement, cross-project resource isolation, parallel request isolation, download authorization after membership removal, account disabling, password reset/change, SECRET rotation, registration controls, last-administrator protection and LLM credential-environment restrictions. Existing tests authenticate through the real login API; no production bypass is provided. Two obsolete duplicate-label rejection expectations were updated to the order-preserving normalization already introduced in 0.14.3.

Six JavaScript unit suites pass: configuration expansion, detail races, model selection, table sorting, error statistics and JSON viewers. The application wheel builds and includes the account module, UI assets and CCA schema. Python compilation and account JavaScript syntax checks pass.

The account browser workflow uses a disposable API and real project-worker supervisor with mock model responses. It verifies login/logout, site-admin account creation, project creation/switching, member administration, read-only controls, isolated task lists, evaluation execution in a new project and project-scoped CSV downloads. The existing codebook and experiment browser workflows also pass, covering imports, task/gold editing, previews, evaluations, binary predictions, sorting, request logs, exports and mobile layout. They use the shared real-login helper in `tests/browser_auth.cjs`. Run browser workflows separately against fresh installations with `CCA_LAB_ADMIN_PASSWORD=browser-password-1234`, a valid SECRET and Playwright Chromium installed. Set `CCA_LAB_TEST_URL` if needed; `CCA_LAB_SCREENSHOT_DIR` controls screenshots. Existing-workflow test credentials can be overridden with `CCA_LAB_TEST_USERNAME` and `CCA_LAB_TEST_PASSWORD`.

Model calls are mocked. Docker, a production HTTPS proxy, live-model performance and large multi-project capacity were not benchmarked. The three Python warnings are existing test-client deprecations and a single-class metric fixture.

# Validation — CCA-Lab 0.14.3

58 targeted Python tests passed: schema compatibility, output order, experiments and compiler variants. Tests check both provider envelopes, both compilers, joint/binary batches, unchanged enum/item bounds, order-preserving label deduplication, candidate matching and rejection of invalid types, unknown IDs and excess distinct labels. No live vLLM server test was performed.

# Validation — CCA-Lab 0.14.2

44 targeted Python tests passed. New tests cover OpenAI-compatible and Ollama length-stop responses with null or incomplete JSON, explicit missing-content errors, per-document doubling beyond the initial UI maximum, ordinary retries without doubling, saved request budgets, pause/resume persistence and retry exhaustion. Model responses are mocked.

# Validation — CCA-Lab 0.14.1

37 targeted Python tests passed (error statistics, minor fixes and experiment execution). Statistics tests cover repeated errors, recovered retries, distinct document counts, final failures, fallbacks, pre-request input errors, empty runs and isolation between jobs. A JavaScript rendering check verifies sortable columns and HTML escaping. The last-error line is replaced only in the individual-run summary; detailed logs remain available.

## Previous full-release validation

# Validation — CCA-Lab 0.14.0

133 Python tests passed, including concurrent endpoint scheduling, same-endpoint serialization, pause/cancel draining, and immutable evaluation snapshots across new evaluations and profile edits. Obsolete executor and migration tests were retired. Current coverage includes codebook-only task validation, rejection of unsupported protocols and database schemas without mutation, preview/execution consistency, batched and binary classification, context, retries, fallbacks, interruption budgets, thinking capture, cancellation, quality/runtime/confidence metrics, reports, exports, and deletion.

Regression checks in `tests/detail_races_unit.cjs` and `tests/model_selection_unit.cjs` cover delayed details/reports, connection switches, stale model lists and editor reopening. JavaScript checks passed for comma-separated parameter expansion, seeds and query estimates, and numeric/text metric sorting with missing values. Run `node tests/configurations_unit.cjs` and `node tests/tables_unit.cjs`. JavaScript syntax checks also passed.

The CCA-Lab wheel builds with the renamed Python package, current executor/compiler, schema and sortable-table assets. No old package namespace is bundled.

Both browser workflows passed using Playwright and Chromium against a disposable API/worker, including sortable metrics and sorting in standalone HTML reports. Browser checks use mocked model responses. `tests/experiments_browser.cjs` covers configuration defaults and expansion, query counts, previews, result-table sorting in both directions with keyboard activation and refresh retention, evaluation, binary prediction, request logs and mobile layout. `tests/cca_browser.cjs` covers CCA file selection/import/edit/export, field validation, gold editing, single-run reporting, error logs, prediction and standalone HTML report sorting. Use a fresh data directory for each workflow and set CCA_LAB_TEST_URL and optionally CCA_LAB_SCREENSHOT_DIR.

Three non-failing Python warnings concern test-client deprecations and a single-class scikit-learn metric fixture. Model calls are mocked. No live-model accuracy/calibration benchmark, GPU throughput benchmark or new 500 MB import benchmark was performed. Docker itself was not run in this environment.

Run the Python suite with `python -m pytest -q`. Use requirements.lock for reproducible dependencies.

Compiler tests cover joint/binary requests, batch sizes, annotation preservation, identical output schemas and distinct evaluation groups across seeds. Shared-viewer tests verify readable newlines, nested JSON decoding, HTML escaping and exact JSON round-trips. Browser tests exercise Compare both, the system compiler preview and switching readable/JSON modes. No claim of improved live-model accuracy is made.
