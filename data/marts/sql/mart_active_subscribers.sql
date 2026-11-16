-- Grain: one row per business_id.
-- active_subscribers is the distinct people with an active subscription in that business.
-- Do not add these rows together. A person active in two businesses is in both rows.
-- subscribers_active recomputes the distinct count from mart_subscription, which is
-- what produces the all-business total. This mart is the per-business check.

select
    business_id,
    count(distinct user_id)::varchar as active_subscribers,
    count(*)::varchar as active_subscriptions
from mart_subscription
where status = 'active'
group by business_id
order by business_id
