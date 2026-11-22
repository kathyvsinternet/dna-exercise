SELECT
  user_geo_country,
  COUNT(DISTINCT user_id) AS n_users,
  ROUND(COUNT(DISTINCT user_id) / SUM(COUNT(DISTINCT user_id)) OVER (), 4) AS n_share
FROM mart_user_info
GROUP BY user_geo_country
ORDER BY n_users DESC, user_geo_country;
