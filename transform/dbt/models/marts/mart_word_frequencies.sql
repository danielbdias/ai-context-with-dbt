with forms as (
    select word, display_word, count(*) as occurrences
    from {{ ref('int_submission_tokens') }}
    group by word, display_word
),

ranked as (
    select
        word,
        display_word,
        sum(occurrences) over (partition by word) as frequency,
        -- Most common spelling, ties broken by the larger string (accented wins).
        row_number() over (
            partition by word order by occurrences desc, display_word desc
        ) as spelling_rank
    from forms
)

select word, display_word, frequency
from ranked
where spelling_rank = 1
