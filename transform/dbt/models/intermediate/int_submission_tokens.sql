{#- One row per word occurrence in a non-deleted message. -#}
with words as (
    select
        submission_id,
        -- ifNull: unit-test fixtures are typed Nullable, arrays can't be.
        arrayJoin(
            extractAll(lowerUTF8(ifNull(message, '')), '\\p{L}+')
        ) as display_word
    from {{ ref('stg_app__submissions') }}
    where not is_deleted
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
where lengthUTF8(word) >= 3
    and word not in (select word from ({{ folded_stopwords() }}))
