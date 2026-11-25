SELECT
  DATE_TRUNC('quarter', date)::DATE as quarter,
  SUM(user_subscriptions) as user_subscriptions,
  SUM(user_cancellations) as user_cancellations
FROM int_daily_users
GROUP BY quarter
ORDER BY quarter;
