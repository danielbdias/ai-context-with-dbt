select
    submission_id,
    message,
    browser,
    os,
    created_at,
    -- Raw timestamps are TIMESTAMP_LTZ, so pin the day to UTC, not the session zone.
    convert_timezone('UTC', created_at)::date as created_date,
    updated_at,
    os in ('iOS', 'Android') as is_mobile,
    length(message) as message_length
from {{ ref('stg_app__submissions') }}
where not is_deleted
