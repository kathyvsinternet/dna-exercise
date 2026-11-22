WITH user_subs AS (
  SELECT start_date AS date,
    COUNT(DISTINCT subscription_id) as user_subscriptions
  FROM fct_subscription
  WHERE is_test_account = 'false'
  GROUP BY date
),
user_cancels AS (
    SELECT end_date AS date, 
      COUNT(DISTINCT subscription_id) as user_cancellations
    FROM fct_subscription
    WHERE is_test_account = 'false' AND status = 'canceled'
    GROUP BY date
)

SELECT * FROM (
  SELECT
    d.date,
    COALESCE(s.user_subscriptions, 0) AS user_subscriptions,
    COALESCE(c.user_cancellations, 0) AS user_cancellations
  FROM int_dates d
  LEFT JOIN user_subs s ON d.date = s.date
  LEFT JOIN user_cancels c ON d.date = c.date
)
WHERE user_subscriptions + user_cancellations > 0
ORDER BY date;