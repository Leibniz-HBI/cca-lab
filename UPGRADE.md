# Installation and restart

New installations create SQLite schema 7 atomically. API and worker may start concurrently.

For an existing current installation, stop both processes, back up the full data directory, replace/rebuild the application, restart both processes and hard-refresh the browser. Startup upgrades schema 6 to 7 atomically, adding request and per-category decision storage. Library tasks become codebook-only: configure their desired execution settings explicitly in new jobs. Existing immutable job snapshots, results and saved exports remain unchanged. Pending jobs retain their recorded execution protocol.

Only the immediately preceding schema 6 is upgraded. Other schema versions or malformed databases stop startup explicitly. Do not point an older application at a schema 7 database.

Worker recovery retains committed document and category decisions. A reserved request interrupted before its outcome is committed consumes an attempt and is marked interrupted; its remote completion and token usage are unknown. Unresolved decisions retry within their remaining budget. Interrupted timings are marked incomplete; interrupted export builds return to pending.
