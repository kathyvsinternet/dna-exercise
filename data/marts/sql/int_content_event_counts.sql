WITH c AS (
  SELECT
    content_id,
    title,
    category,
    content_type,
    publish_date,
    runtime_minutes AS duration_min
  FROM dim_content
),
e AS (
  SELECT
    content_id,
    event_type,
    COUNT(DISTINCT event_id) AS n_events
  FROM fct_engagement_event
  -- select a few events to display for content engagement
  WHERE event_type IN ('content_complete', 'content_open', 'download')
    -- exclude events from test accounts
    AND is_test_account = 'false'
  GROUP BY content_id, event_type
)
SELECT 
  c.*, 
  e.event_type, 
  e.n_events 
FROM c
INNER JOIN e USING(content_id)