# Research workflow in TextLab 0.5

The sidebar follows five steps. These are navigation aids, not locked stages: you can return to any step at any time.

| Step | Purpose |
|---|---|
| 1 · Define tasks | Develop the codebook, examples, decision rules and optional outputs |
| 2 · Prepare data | Import corpus files, inspect datasets and register gold labels |
| 3 · Evaluate & refine | Compare model configurations and seeds, inspect errors and revise tasks |
| 4 · Run predictions | Apply tasks or evaluated configurations to a target corpus |
| 5 · Analyze & export | Find completed evaluations, prediction batches and standalone jobs; open results and download outputs |

**Jobs & monitoring** sits below the numbered workflow with an active/queued counter. The counter uses the latest 500 jobs; running, queued and draining pause/cancel requests count as active. Paused jobs remain accessible in the monitor. **LLM connections** is in a separate **Configuration** section at the bottom, accessible on desktop and mobile.

Prepare data contains **Corpus & CSV files** and **Gold datasets** tabs. Original CSV deletion, dataset previews, gold mapping and all previous deletion controls remain available. Existing `#datasets` and `#gold` URLs continue to work and highlight step 2.

## Contextual shortcuts

- **Evaluate this task** opens evaluation setup with that task selected. A gold registration and connection are still needed before an evaluation can be configured.
- **Register gold labels** opens column mapping for the selected imported dataset.
- **Use this dataset** opens multi-task prediction setup with the selected corpus.
- **Revise task** in an evaluation opens its evaluated codebook. If that revision is still current, saving creates the next revision. If the library task was changed or deleted, the editor starts a separate copy from the evaluated snapshot. Nothing is saved until you submit the editor; historical evaluation snapshots are unchanged.
- **Use configuration for prediction** appears for completed evaluation runs. It copies the selected run's model, temperature, seed, sampling parameters, output settings, concurrency, retries, text handling and additional API parameters into prediction setup. Choose your target corpus and review the copied parameters before starting. Multiple seeds can still be entered.

Reusing an evaluation preserves its exact evaluated task revision and connection snapshot. These two fields are fixed for that reuse flow, while model/query parameters remain editable. The saved task/profile need not still exist in the library. This avoids silently applying a revised codebook or altered endpoint. Use ordinary prediction setup when you want to choose different tasks or a different connection.

New prediction snapshots include `source_evaluation_job_id` and `source_evaluation_id` for provenance. Reuse does not copy labels or gold annotations into prompts. The source run must be a completed evaluation run; active, paused, cancelled and standalone classification jobs cannot be used through this shortcut.

## Analyze & export

The hub lists evaluations whose reports are ready, prediction batches whose files are ready and terminal standalone classification jobs. Filter by output type. Open an evaluation for mean/SD metrics, per-class tables, charts and detailed predictions; download a report ZIP or metrics CSV directly. Prediction files and standalone job exports also have direct links.

Child jobs remain within their parent evaluation/prediction rather than appearing as duplicate standalone outputs. They are still accessible from Jobs & monitoring. Each type is limited to the latest 500 entries, matching existing API list limits. This hub organizes existing outputs; it does not combine unrelated evaluations into a new pooled analysis.

## API and upgrade

`POST /api/predictions` now accepts optional `source_evaluation_job_id`. With this field, `task_ids` must contain exactly the evaluated task ID, and the saved task/connection are loaded from that run. The required `profile_id` may be `"snapshot"` because the source run supplies the connection. The request's query, seeds, target dataset and text column control the new run. Without the source field, the previous API behavior is unchanged.

Job list/detail responses expose parent `evaluation_id` and `prediction_id` for organizing results. Startup validates database schema 6 without migrating it. Stop both processes, replace/rebuild the application and restart using your existing data volume. Reload the browser to load the new frontend.
