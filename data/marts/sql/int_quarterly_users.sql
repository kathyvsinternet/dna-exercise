SELECT
  DATE_TRUNC('quarter', date)::DATE as quarter,
  SUM(user_signups) as user_signups,
  SUM(user_subscriptions) as user_subscriptions,
  SUM(user_cancels) as user_cancels
FROM int_daily_users
GROUP BY quarter
ORDER BY quarter;
