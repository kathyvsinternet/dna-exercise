-- Grain: one row per business_id, plan_tier, billing_cycle, and status.
-- subscriptions is additive. plans_active and plans_paid_active sum it.
-- There is no subscriber count. A person can sit in more than one group,
-- so a distinct count does not belong on this grain.

select
    business_id,
    plan_tier,
    billing_cycle,
    status,
    count(*)::varchar as subscriptions,
    count(*) filter (where monthly_price_is_invalid = 'true')::varchar as invalid_price_subscriptions,
    printf(
        '%.2f',
        coalesce(sum(
            case
                when monthly_price_is_invalid = 'false' and monthly_price_usd <> ''
                then monthly_price_usd::double
            end
        ), 0)
    ) as monthly_price_usd_sum
from mart_subscription
group by business_id, plan_tier, billing_cycle, status
order by business_id, plan_tier, billing_cycle, status
