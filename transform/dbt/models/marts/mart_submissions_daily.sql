{{ config(materialized='table', order_by='day') }}

with daily as (
    select created_date as day, count() as submissions_count
    from {{ ref('fct_submissions') }}
    group by created_date
)

select
    day,
    submissions_count,
    sum(submissions_count) over (
        order by day rows between unbounded preceding and current row
    ) as cumulative_submissions
from daily
