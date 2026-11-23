SELECT 
  *,
  ROUND(n_subs_active / n_users_active, 4) AS avg_subs,
  ROUND(n_subs_paid / n_users_active, 4) AS avg_subs_paid,
  ROUND(n_subs_free / n_users_active, 4) AS avg_subs_free,
  ROUND(total_monthly_payment / n_users_active, 2) AS avg_monthly_payment
FROM (
  SELECT
    COUNT(DISTINCT user_id) AS n_users_active,
    SUM(n_subs_active) AS n_subs_active,
    SUM(n_subs_paid) AS n_subs_paid,
    SUM(n_subs_free) AS n_subs_free,
    SUM(n_subs_basic) AS n_subs_basic,
    SUM(monthly_payment) AS total_monthly_payment
  FROM ( SELECT * FROM int_user_info ) )