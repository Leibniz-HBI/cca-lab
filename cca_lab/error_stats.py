"""Error frequencies from committed document results, including recovered retries."""

def error_statistics(db, job_id):
    # Read only the compact attempt metadata, never raw responses or source texts.
    rows = db.execute("""
        WITH affected AS (
            SELECT row_no,status,error,attempt_outputs FROM results
            WHERE job_id=? AND (error_count>0 OR error IS NOT NULL)
        ), events AS (
            SELECT r.row_no,r.status,json_extract(a.value,'$.error') AS message
            FROM affected r, json_each(r.attempt_outputs) a
            WHERE json_extract(a.value,'$.error') IS NOT NULL
              AND json_extract(a.value,'$.error')!=''
            UNION ALL
            SELECT r.row_no,r.status,r.error FROM affected r
            WHERE r.error IS NOT NULL AND r.error!='' AND NOT EXISTS (
                SELECT 1 FROM json_each(r.attempt_outputs) a
                WHERE json_extract(a.value,'$.error') IS NOT NULL
                  AND json_extract(a.value,'$.error')!=''
            )
        )
        SELECT message,COUNT(*) AS occurrences,COUNT(DISTINCT row_no) AS documents,
            COUNT(DISTINCT CASE WHEN status='ok' THEN row_no END) AS recovered,
            COUNT(DISTINCT CASE WHEN status='failed' THEN row_no END) AS failed,
            COUNT(DISTINCT CASE WHEN status='fallback' THEN row_no END) AS fallbacks
        FROM events GROUP BY message ORDER BY occurrences DESC,message
    """, (job_id,)).fetchall()
    totals = db.execute("""SELECT COUNT(*) AS documents,
        COALESCE(SUM(status='ok'),0) AS recovered,
        COALESCE(SUM(status='failed'),0) AS failed,
        COALESCE(SUM(status='fallback'),0) AS fallbacks
        FROM results WHERE job_id=? AND (error_count>0 OR error IS NOT NULL)
    """, (job_id,)).fetchone()
    return {**dict(totals), 'occurrences':sum(r['occurrences'] for r in rows),
            'by_error':[dict(r) for r in rows]}
