SELECT 
  content_id, 
  title, 
  category, 
  content_type, 
  publish_date, 
  duration_min, 
  SUM(CASE WHEN event_type = 'content_complete' THEN n_events ELSE 0 END) AS n_content_complete,
  SUM(CASE WHEN event_type = 'content_open' THEN n_events ELSE 0 END) AS n_content_open,
  SUM(CASE WHEN event_type = 'download' THEN n_events ELSE 0 END) AS n_download,
  SUM(n_events) as n_engagement_events
FROM int_content_event_counts
GROUP BY ALL
ORDER BY n_engagement_events DESC, content_id