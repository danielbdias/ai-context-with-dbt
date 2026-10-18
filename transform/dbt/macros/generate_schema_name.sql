{#- Use the custom schema verbatim (staging, marts) instead of the default
    <target schema>_<custom schema>, which would build staging_marts.
    Seeds have no custom schema of their own and land in staging. -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is not none -%}
        {{ custom_schema_name | trim }}
    {%- elif node.resource_type == 'seed' -%}
        staging
    {%- else -%}
        {{ target.schema }}
    {%- endif -%}
{%- endmacro %}
