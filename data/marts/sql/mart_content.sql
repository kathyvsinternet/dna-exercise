-- Grain: one row per content_id.
-- Event counts exclude test accounts. A title with no remaining events stays here with zeros.
-- Opens and completes are not a governed metric. This mart is for an analyst, not for Ask.

with events as (
    select *
    from fct_engagement_event
    where is_test_account = 'false'
      and content_id <> ''
)
select
    content.content_id,
    content.business_id,
    content.title,
    content.category,
    content.content_type,
    content.creator_id,
    count(events.event_id)::varchar as events,
    count(events.event_id) filter (where events.event_type = 'content_open')::varchar as content_opens,
    count(events.event_id) filter (where events.event_type = 'content_complete')::varchar as content_completes,
    count(events.event_id) filter (where events.event_type = 'like')::varchar as likes,
    count(events.event_id) filter (where events.event_type = 'share')::varchar as shares,
    count(events.event_id) filter (where events.event_type = 'comment_post')::varchar as comments,
    count(events.event_id) filter (where events.event_type = 'download')::varchar as downloads,
    count(events.event_id) filter (
        where events.event_type not in (
            'content_open', 'content_complete', 'like', 'share', 'comment_post', 'download'
        )
    )::varchar as other_events,
    count(events.event_id) filter (where events.session_duration_sec <> '')::varchar as events_with_valid_duration,
    coalesce(sum(
        case
            when events.session_duration_sec <> '' then events.session_duration_sec::bigint
        end
    ), 0)::varchar as session_duration_sec_sum
from dim_content as content
left join events on events.content_id = content.content_id
group by
    content.content_id,
    content.business_id,
    content.title,
    content.category,
    content.content_type,
    content.creator_id
order by content.content_id
