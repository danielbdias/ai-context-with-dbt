{#- One row per word occurrence in a non-deleted message. A word is a run of
    Latin letters, accented ones included. Snowflake regex has no \p{L}. -#}
with words as (
    select
        stg.submission_id,
        piece.value::string as display_word
    from {{ ref('stg_app__submissions') }} as stg,
        lateral flatten(
            input => regexp_substr_all(lower(coalesce(stg.message, '')), '[a-zà-öø-ÿ]+')
        ) as piece
    where not stg.is_deleted
),

tokens as (
    select
        submission_id,
        display_word,
        {{ normalize_token('display_word') }} as word
    from words
)

select submission_id, word, display_word
from tokens
where length(word) >= 3
    and word not in (select word from ({{ folded_stopwords() }}))
