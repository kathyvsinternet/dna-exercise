-- Grain: one row per business_id, plan_tier, and start month.
-- A start counts even when the subscription is later canceled, paused, or unknown.
-- plan_starts is additive across businesses, plan tiers, and months.
-- The metric sums this column. It does not count rows of fct_subscription.

select
    business_id,
    plan_tier,
    start_month as start_date_month,
    count(*)::varchar as plan_starts
from mart_subscription
where start_date <> ''
group by business_id, plan_tier, start_month
order by business_id, plan_tier, start_month
