{% test no_stopwords(model, column_name) %}
{#- Fails for every row whose folded value is a PT or EN stopword. -#}
select {{ column_name }} as offending_word
from {{ model }}
where {{ normalize_token(column_name) }} in (select word from ({{ folded_stopwords() }}))
{% endtest %}
