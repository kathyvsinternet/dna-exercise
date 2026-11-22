-- intermediate model for daily activity counts

WITH user_signups AS (
  SELECT signup_date AS date,
    COUNT(DISTINCT user_id) as user_signups
  FROM dim_user
  WHERE is_test_account = 'false'
  GROUP BY date
),
user_subs AS (
  SELECT start_date AS date,
    COUNT(DISTINCT subscription_id) as user_subscriptions
  FROM fct_subscription
  WHERE is_test_account = 'false'
  GROUP BY date
),
user_cancels AS (
    SELECT end_date AS date, 
      COUNT(DISTINCT subscription_id) as user_cancels
    FROM fct_subscription
    WHERE is_test_account = 'false' AND status = 'canceled'
    GROUP BY date
)

SELECT * FROM (
  SELECT
    d.date,
    COALESCE(u.user_signups, 0) AS user_signups,
    COALESCE(s.user_subscriptions, 0) AS user_subscriptions,
    COALESCE(c.user_cancels, 0) AS user_cancels
  FROM int_dates d
  LEFT JOIN user_signups u ON d.date = u.date
  LEFT JOIN user_subs s ON d.date = s.date
  LEFT JOIN user_cancels c ON d.date = c.date
)
WHERE user_signups + user_subscriptions + user_cancels > 0
ORDER BY date;