# Installation and restart

Use an empty data directory for a new installation. Startup creates the complete current SQLite schema (ID 6) in one transaction. API and worker startup may run concurrently.

To replace the application, stop API and worker, replace/rebuild the source, restart both processes, and hard-refresh the browser. Existing current-schema databases and cca-reference-v2 snapshots are supported without rewriting tasks, results or reports. No incremental migrations or old prompt compilers are included. Unsupported database schemas stop startup with an explicit error.

Worker recovery remains active: interrupted timing is marked incomplete and interrupted export builds return to pending. Persisted classification results are retained.
