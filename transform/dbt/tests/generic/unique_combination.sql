{% test unique_combination(model, combination_columns) %}
{#- Fails for every combination of the given columns that appears twice. -#}
select {{ combination_columns | join(', ') }}, count() as occurrences
from {{ model }}
group by {{ combination_columns | join(', ') }}
having count() > 1
{% endtest %}
