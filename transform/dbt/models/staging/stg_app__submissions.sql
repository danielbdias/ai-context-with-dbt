{#- Latest version of every submission. raw.submissions keeps one row per id
    after the dlt merge, but max_by makes this robust to duplicates. -#}
with latest as (
    select
        id as submission_id,
        max_by(message, updated_at) as latest_message,
        max_by(browser_family, updated_at) as raw_browser_family,
        max_by(os_family, updated_at) as raw_os_family,
        max_by(created_at, updated_at) as first_created_at,
        max(updated_at) as last_updated_at,
        -- max_by keeps a NULL winner, so an un-delete stays the latest state.
        max_by(deleted_at, updated_at) as latest_deleted_at
    from {{ source('app', 'submissions') }}
    group by id
)

select
    latest.submission_id as submission_id,
    latest.latest_message as message,
    -- A left join yields NULL when nothing matches.
    coalesce(browsers.browser_family, 'Other') as browser,
    coalesce(systems.os_family, 'Other') as os,
    latest.first_created_at as created_at,
    latest.last_updated_at as updated_at,
    latest.latest_deleted_at as deleted_at,
    latest.latest_deleted_at is not null as is_deleted
from latest
left join {{ ref('browser_family_map') }} as browsers
    on latest.raw_browser_family = browsers.raw_family
left join {{ ref('os_family_map') }} as systems
    on latest.raw_os_family = systems.raw_family
