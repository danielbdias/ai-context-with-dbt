{#- dbt 2.0.8 workaround: the built-in ClickHouse freshness query returns
    UInt32 epoch seconds (toUnixTimestamp and now()), which dbt's own type
    check then rejects as "not a timestamp". Return real timestamps instead. -#}
{% macro clickhouse__collect_freshness(source, loaded_at_field, filter) -%}
    {% call statement('collect_freshness', fetch_result=True, auto_begin=False) -%}
        select
            max({{ loaded_at_field }}) as max_loaded_at,
            now64(6, 'UTC') as snapshotted_at
        from {{ source }}
        {% if filter %}where {{ filter }}{% endif %}
    {%- endcall %}
    {{ return(load_result('collect_freshness')) }}
{%- endmacro %}
