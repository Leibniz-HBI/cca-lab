# Upgrade to TextLab 0.7.0

1. Stop both the API and worker. Back up the complete data directory/volume.
2. Replace the source code in the existing project directory. Retain your `.env`, data directory and Compose project name.
3. Rebuild/restart both processes with the same data location.

```bash
docker compose down
# Replace source files with this release; preserve .env and the data volume.
docker compose up --build -d
```

Do not use `down -v`. Changing the Compose project directory/name can select a different named volume; use the original project name with `docker compose -p NAME ...` if necessary.

For direct Python installations, stop both processes, replace source, activate the environment, install `requirements.lock` and `pip install --no-deps -e .`, then restart both with the original `TEXTLAB_DATA`.

The idempotent additive migration creates prediction tables and job timing columns and sets schema version 6. Existing tasks, profiles, input records, jobs and results remain. Missing task thinking settings use server default; missing profile adapters use Auto. Job overrides inherit task settings when null.

When migrating older timing/error schemas, evaluation reports are invalidated once and rebuilt by the worker so they gain the new report structure and English policy text. Historical active/elapsed timing cannot be reconstructed and appears as n/a. Existing per-document durations remain available. User-authored text is not translated.

Do not run an older worker against the upgraded database. For rollback, stop both processes and restore the previous source and complete pre-upgrade backup together.

Version 0.4 also adds error counters/indexing and fallback counters, backfills existing error records, and rebuilds evaluation reports with seed aggregates. This can take time on a large result database. Existing tasks have no fallback by default; historical outputs are unchanged. See REPETITIONS.md.

Version 0.5 changes the workflow UI and adds evaluated-configuration reuse. Schema version remains 4. Existing data and URLs remain usable. Reload the browser after replacing the application. See WORKFLOW.md.

Version 0.6 adds nullable self-reported confidence and structured-alternatives columns (schema 5). Older tasks default both options off; old snapshots/results and existing prediction artifacts are retained. Old reports show confidence n/a; new experiments include the diagnostics. New prediction batches persist agreement CSV/JSONL. Reload the browser after upgrading. See UNCERTAINTY.md.

Version 0.7 adds the candidate_interpretations column (schema 6) and fixes the prompt protocol to evidence-first-v1. Historical alternatives, results and saved artifacts are retained. Existing field-enable switches still work, but there is no ordering option. Finish pending jobs with the previous worker before upgrading if experiments must not mix generation protocols. A resumed old job uses the new prompt for remaining requests; attempt logs record the protocol. Re-evaluate reused historical configurations under the new prompt before relying on their previous quality measurements. See UNCERTAINTY.md.
