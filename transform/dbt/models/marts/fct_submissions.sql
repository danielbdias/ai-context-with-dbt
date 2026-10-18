{{ config(materialized='table', order_by='submission_id') }}

select
    submission_id,
    message,
    browser,
    os,
    created_at,
    toDate(created_at) as created_date,
    updated_at
from {{ ref('stg_app__submissions') }}
where not is_deleted
