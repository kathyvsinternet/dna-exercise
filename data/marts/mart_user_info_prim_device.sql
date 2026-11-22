SELECT
  user_prim_device,
  COUNT(DISTINCT user_id) AS n_users,
  ROUND(COUNT(DISTINCT user_id) / SUM(COUNT(DISTINCT user_id)) OVER (), 4) AS n_share
FROM mart_user_info
GROUP BY user_prim_device
ORDER BY n_users DESC, user_prim_device;
