-- Grain: one row per subscription held by a real account.
-- Test accounts are removed here. A metric on this mart does not filter them again.
-- user_id is the subscriber key for distinct counts. Names, emails, and age bands are not here.
-- subscribers_active counts distinct user_id on this mart. The business totals are not additive.

select
    subscription_id,
    user_id,
    business_id,
    plan_tier,
    billing_cycle,
    status,
    start_date,
    substr(start_date, 1, 7) as start_month,
    monthly_price_usd,
    monthly_price_is_invalid
from fct_subscription
where is_test_account = 'false'
order by subscription_id
