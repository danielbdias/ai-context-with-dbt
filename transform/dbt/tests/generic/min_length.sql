{% test min_length(model, column_name, min_length) %}
{#- Fails for every row whose value has fewer than min_length characters. -#}
select {{ column_name }} as offending_value
from {{ model }}
where lengthUTF8({{ column_name }}) < {{ min_length }}
{% endtest %}
