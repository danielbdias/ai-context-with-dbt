select
    browser,
    os,
    count(*) as submissions_count,
    row_number() over (order by count(*) desc, browser, os) as popularity_rank
from {{ ref('fct_submissions') }}
group by browser, os
