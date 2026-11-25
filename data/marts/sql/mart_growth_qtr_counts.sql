-- Here we calculate churn rate by looking at the previous quarter end's net subscriptions
-- then we take the current quarter's cancellations and divide

SELECT
  quarter,
  user_subscriptions,
  user_cancellations,
  SUM(user_subscriptions - user_cancellations) OVER thru_curr AS running_net_subscriptions,
  ROUND(user_cancellations / NULLIF(SUM(user_subscriptions - user_cancellations) OVER pre_curr, 0), 4) AS quarterly_churn_rate
FROM int_user_qtr_counts
WINDOW
  thru_curr AS (ORDER BY quarter), -- goes through existing row's quarter
  pre_curr AS (ORDER BY quarter ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) -- ends at previous row's quarter
ORDER BY quarter;
