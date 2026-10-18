{#- Fails (returns a row) when browser or OS counts do not add up to the fact. -#}
with fact as (
    select count() as total from {{ ref('fct_submissions') }}
),
browsers as (
    select sum(submissions_count) as total from {{ ref('mart_browser_distribution') }}
),
systems as (
    select sum(submissions_count) as total from {{ ref('mart_os_distribution') }}
)
select
    fact.total as fact_total,
    browsers.total as browser_total,
    systems.total as os_total
from fact, browsers, systems
where browsers.total != fact.total or systems.total != fact.total
