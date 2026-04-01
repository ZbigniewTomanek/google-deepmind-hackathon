# SQL Queries for Job Monitoring

## Job summary (aggregate counts)

```sql
SELECT
    count(*) FILTER (WHERE status = 'todo') AS todo,
    count(*) FILTER (WHERE status = 'doing') AS doing,
    count(*) FILTER (WHERE status = 'succeeded') AS succeeded,
    count(*) FILTER (WHERE status = 'failed') AS failed,
    count(*) AS total
FROM procrastinate_jobs
WHERE queue_name = 'extraction'
  AND ($1::text IS NULL OR args->>'agent_id' = $1);
```

## Job list (with pagination and filters)

```sql
SELECT j.id, j.task_name, j.status, j.queue_name, j.args, j.attempts,
       j.scheduled_at, j.started_at,
       (SELECT MIN(at) FROM procrastinate_events e
        WHERE e.job_id = j.id AND e.type = 'deferred') AS created_at,
       (SELECT MAX(at) FROM procrastinate_events e
        WHERE e.job_id = j.id AND e.type IN ('succeeded', 'failed')) AS finished_at
FROM procrastinate_jobs j
WHERE j.queue_name = 'extraction'
  AND ($1::text IS NULL OR j.args->>'agent_id' = $1)
  AND ($2::text IS NULL OR j.status::text = $2)
  AND ($3::text IS NULL OR j.task_name = $3)
ORDER BY j.id DESC
LIMIT $4 OFFSET $5;
```

## Single job detail

```sql
SELECT j.id, j.task_name, j.status, j.queue_name, j.args, j.attempts,
       j.scheduled_at, j.started_at
FROM procrastinate_jobs j
WHERE j.id = $1;
```

## Job event timeline

```sql
SELECT type, at
FROM procrastinate_events
WHERE job_id = $1
ORDER BY at ASC;
```

## Cancel a queued job

```sql
UPDATE procrastinate_jobs
SET status = 'failed'
WHERE id = $1 AND status = 'todo'
RETURNING id;
```

## Insert cancellation event

```sql
INSERT INTO procrastinate_events (job_id, type, at)
VALUES ($1, 'cancelled', NOW());
```

## Useful diagnostic queries

### Jobs stuck in 'doing' for >10 minutes
```sql
SELECT id, task_name, args, started_at,
       NOW() - started_at AS running_for
FROM procrastinate_jobs
WHERE status = 'doing'
  AND started_at < NOW() - INTERVAL '10 minutes'
ORDER BY started_at;
```

### Recent failures with args
```sql
SELECT j.id, j.task_name, j.args, j.attempts,
       e.at AS failed_at
FROM procrastinate_jobs j
JOIN procrastinate_events e ON e.job_id = j.id AND e.type = 'failed'
WHERE j.status = 'failed'
ORDER BY e.at DESC
LIMIT 20;
```
