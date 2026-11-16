-- Grain: one row per business.
-- A house summary for an analyst. subscribers counts every status, so it is not
-- subscribers_active. active_subscriptions matches plans_active for that business.
-- Engagement counts events on this business's content, excluding test accounts.
-- Events with no content id have no business, so they stay off this mart.

with subscription_counts as (
    select
        business_id,
        count(*) as subscriptions,
        count(*) filter (where status = 'active') as active_subscriptions,
        count(*) filter (where status = 'canceled') as canceled_subscriptions,
        count(*) filter (where status = 'paused') as paused_subscriptions,
        count(*) filter (where status = 'trialing') as trialing_subscriptions,
        count(*) filter (where status = 'unknown') as unknown_status_subscriptions,
        count(distinct user_id) as subscribers,
        coalesce(sum(
            case
                when status = 'active' and monthly_price_usd <> ''
                then monthly_price_usd::double
            end
        ), 0) as active_monthly_price_usd
    from mart_subscription
    group by business_id
),
content_counts as (
    select
        business_id,
        count(*) as content_items,
        count(*) filter (where content_type = 'unknown') as unknown_type_content_items
    from dim_content
    group by business_id
),
creator_counts as (
    select business_id, count(*) as creators
    from dim_creator
    group by business_id
),
event_counts as (
    select
        content.business_id,
        count(*) as engagement_events,
        count(distinct event.content_id) as content_items_with_engagement
    from fct_engagement_event as event
    join dim_content as content on content.content_id = event.content_id
    where event.is_test_account = 'false'
      and event.content_id <> ''
    group by content.business_id
)
select
    business.business_id,
    business.business_name,
    business.business_line,
    coalesce(content_counts.content_items, 0)::varchar as content_items,
    coalesce(content_counts.unknown_type_content_items, 0)::varchar as unknown_type_content_items,
    coalesce(creator_counts.creators, 0)::varchar as creators,
    coalesce(subscription_counts.subscriptions, 0)::varchar as subscriptions,
    coalesce(subscription_counts.active_subscriptions, 0)::varchar as active_subscriptions,
    coalesce(subscription_counts.canceled_subscriptions, 0)::varchar as canceled_subscriptions,
    coalesce(subscription_counts.paused_subscriptions, 0)::varchar as paused_subscriptions,
    coalesce(subscription_counts.trialing_subscriptions, 0)::varchar as trialing_subscriptions,
    coalesce(subscription_counts.unknown_status_subscriptions, 0)::varchar as unknown_status_subscriptions,
    coalesce(subscription_counts.subscribers, 0)::varchar as subscribers,
    printf('%.2f', coalesce(subscription_counts.active_monthly_price_usd, 0)) as active_monthly_price_usd,
    coalesce(event_counts.engagement_events, 0)::varchar as engagement_events,
    coalesce(event_counts.content_items_with_engagement, 0)::varchar as content_items_with_engagement
from dim_business as business
left join subscription_counts on subscription_counts.business_id = business.business_id
left join content_counts on content_counts.business_id = business.business_id
left join creator_counts on creator_counts.business_id = business.business_id
left join event_counts on event_counts.business_id = business.business_id
order by business.business_id
