{{ config(materialized='table', order_by='word') }}

with forms as (
    select word, display_word, count() as occurrences
    from {{ ref('int_submission_tokens') }}
    group by word, display_word
)

select
    word,
    -- Most common spelling, ties broken by the larger string (accented wins).
    argMax(display_word, tuple(occurrences, display_word)) as display_word,
    sum(occurrences) as frequency
from forms
group by word
