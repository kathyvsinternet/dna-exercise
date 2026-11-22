WITH subs AS (
  SELECT
    user_id,
    subscription_id,
    business_id,
    plan_tier,
    monthly_price_usd,
  FROM fct_subscription
  WHERE status = 'active'
    AND is_test_account = 'false'
),
user_subs AS (
  SELECT
    user_id,
    COUNT(DISTINCT subscription_id) AS n_subs_active,
    COUNT(CASE WHEN plan_tier = 'Free' THEN subscription_id END) AS n_subs_free,
    COUNT(CASE WHEN plan_tier = 'Basic' THEN subscription_id END) AS n_subs_basic,
    SUM(monthly_price_usd) AS monthly_payment
  FROM subs
  GROUP BY user_id
)

SELECT 
  s.* 
  i.country AS user_geo_country,
  i.age_band AS user_age_band,
  i.acquisition_channel AS user_acq_channel
  i.primary_device AS user_prim_device
FROM user_subs s
LEFT JOIN dim_user i 
ON s.user_id = i.user_id
