{#- Relation-free SQL: every stopword (PT and EN seeds), folded like tokens. -#}
{% macro folded_stopwords() -%}
    select distinct {{ normalize_token('word') }} as word
    from (
        select word from {{ ref('stopwords_pt') }}
        union all
        select word from {{ ref('stopwords_en') }}
    )
{%- endmacro %}
