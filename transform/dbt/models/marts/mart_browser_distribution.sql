{{ config(materialized='table', order_by='browser') }}

select
    browser,
    count() as submissions_count,
    round(100 * count() / sum(count()) over (), 2) as pct
from {{ ref('fct_submissions') }}
group by browser
