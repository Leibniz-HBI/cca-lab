# Validation — TextLab 0.12.0

139 Python tests passed. New coverage exercises both provider request shapes, joint/binary strategy, batching and context combinations; empty label sets; partial retries; shared token accounting; binary component aggregation and fallback; pause/resume and interrupted request budgets; HTTP failure handling; configuration expansion; preview endpoints; Parquet and request exports; and the schema 6→7 upgrade preserving saved snapshots. Existing CCA, quality/runtime, confidence, repetition, deletion, error-log and current-snapshot regression checks remain included.

The Playwright/Chromium experiment workflow passed configuration defaults, variation generation, planned query counts, actual-data prompt previews, evaluation completion, binary prediction, request logs, exports and mobile overflow checks, with no JavaScript or HTTP 5xx errors. Desktop and mobile screenshots were inspected. The separate CCA browser workflow also passed actual file selection across refresh, invalid-file feedback, create/edit/export, criteria and context preservation, gold editing, single-run SD omission, evaluation, prediction, error logs and desktop/mobile task-import layouts.

JavaScript syntax checks passed. A 0.12.0 wheel built successfully, and its contents include the new compiler, executor, configuration UI and database schema.

Three non-failing Python warnings concern test-client deprecations and a single-class scikit-learn metric fixture. Model calls were mocked. No live-model accuracy/calibration benchmark, GPU throughput benchmark or new 500 MB import benchmark was performed.

Run Python checks with `python -m pytest -q`. Browser checks require Playwright, Chromium and a disposable API/worker with an empty data directory:

```
TEXTLAB_TEST_URL=http://127.0.0.1:8099 node tests/experiments_browser.cjs
```

Use a separate empty data directory for `node tests/cca_browser.cjs`. Optional `TEXTLAB_SCREENSHOT_DIR` controls screenshot output. Browser tests create test data and model connections. Use requirements.lock for reproducible Python dependencies.
