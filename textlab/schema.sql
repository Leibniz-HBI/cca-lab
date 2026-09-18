CREATE TABLE tasks (
          id TEXT PRIMARY KEY, revision INTEGER NOT NULL, spec TEXT NOT NULL, updated REAL NOT NULL);
CREATE TABLE profiles (
          id TEXT PRIMARY KEY, spec TEXT NOT NULL);
CREATE TABLE datasets (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL, bytes INTEGER NOT NULL,
          delimiter TEXT NOT NULL, encoding TEXT NOT NULL, status TEXT NOT NULL,
          columns_json TEXT NOT NULL DEFAULT '[]', total INTEGER NOT NULL DEFAULT 0,
          error TEXT, created REAL NOT NULL);
CREATE TABLE records (
          dataset_id TEXT NOT NULL REFERENCES datasets(id), row_no INTEGER NOT NULL,
          data TEXT NOT NULL, PRIMARY KEY(dataset_id,row_no)) WITHOUT ROWID;
CREATE TABLE jobs (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, dataset_id TEXT NOT NULL REFERENCES datasets(id),
          snapshot TEXT NOT NULL, status TEXT NOT NULL, total INTEGER NOT NULL,
          done INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0,
          cursor INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, updated REAL NOT NULL,
          last_error TEXT, requests INTEGER NOT NULL DEFAULT 0,
          prompt_tokens INTEGER NOT NULL DEFAULT 0, completion_tokens INTEGER NOT NULL DEFAULT 0,
          total_seconds REAL NOT NULL DEFAULT 0, started_at REAL, finished_at REAL, active_seconds REAL NOT NULL DEFAULT 0, active_since REAL, runtime_complete INTEGER NOT NULL DEFAULT 0, fallback_count INTEGER NOT NULL DEFAULT 0);
CREATE TABLE results (
          job_id TEXT NOT NULL REFERENCES jobs(id), row_no INTEGER NOT NULL,
          labels TEXT NOT NULL, rationale TEXT, status TEXT NOT NULL, error TEXT,
          raw TEXT, attempts INTEGER NOT NULL, seconds REAL NOT NULL,
          prompt_tokens INTEGER NOT NULL, completion_tokens INTEGER NOT NULL, candidate_interpretations TEXT NOT NULL DEFAULT '[]', self_reported_confidence REAL, alternative_interpretations TEXT NOT NULL DEFAULT '[]', evidence TEXT NOT NULL DEFAULT '[]', thinking TEXT, attempt_outputs TEXT NOT NULL DEFAULT '[]', error_count INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY(job_id,row_no)) WITHOUT ROWID;
CREATE TABLE worker_state (
          id INTEGER PRIMARY KEY CHECK(id=1), heartbeat REAL NOT NULL);
CREATE TABLE gold_sets (
          id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL REFERENCES datasets(id),
          spec TEXT NOT NULL, total INTEGER NOT NULL, label_counts TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE gold_rows (
          gold_id TEXT NOT NULL REFERENCES gold_sets(id), row_no INTEGER NOT NULL,
          doc_id TEXT NOT NULL, labels TEXT NOT NULL,
          PRIMARY KEY(gold_id,row_no), UNIQUE(gold_id,doc_id)) WITHOUT ROWID;
CREATE TABLE evaluations (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, gold_id TEXT NOT NULL REFERENCES gold_sets(id),
          task_snapshot TEXT NOT NULL, created REAL NOT NULL,
          report_json TEXT, report_error TEXT);
CREATE TABLE evaluation_runs (
          evaluation_id TEXT NOT NULL REFERENCES evaluations(id),
          job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id), name TEXT NOT NULL, ordinal INTEGER NOT NULL,
          PRIMARY KEY(evaluation_id,job_id)) WITHOUT ROWID;
CREATE TABLE predictions (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, dataset_id TEXT NOT NULL REFERENCES datasets(id),
          created REAL NOT NULL, artifact_status TEXT NOT NULL DEFAULT 'pending', artifact_error TEXT);
CREATE TABLE prediction_runs (
          prediction_id TEXT NOT NULL REFERENCES predictions(id), job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id),
          task_name TEXT NOT NULL, ordinal INTEGER NOT NULL, PRIMARY KEY(prediction_id,job_id)) WITHOUT ROWID;
CREATE TABLE prediction_artifacts (
          prediction_id TEXT NOT NULL REFERENCES predictions(id), format TEXT NOT NULL,
          path TEXT NOT NULL, bytes INTEGER NOT NULL, PRIMARY KEY(prediction_id,format)) WITHOUT ROWID;
CREATE INDEX result_errors ON results(job_id,row_no) WHERE error_count>0;
