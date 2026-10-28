{#- Use the custom schema verbatim (staging, marts) instead of the default
    <target schema>_<custom schema>, which would build staging_marts. That holds
    for the named targets that own the shared schemas (dev, ci, mcp, charts and
    a dbt platform environment whose target name is prod). Any other target, such
    as a developer's own platform environment, builds into <its schema>_<custom>
    so it cannot overwrite the shared marts.
    Seeds have no custom schema of their own and land in staging. -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set shared_targets = ['dev', 'ci', 'mcp', 'charts', 'prod'] -%}
    {%- if custom_schema_name is not none and target.name in shared_targets -%}
        {{ custom_schema_name | trim }}
    {%- elif custom_schema_name is not none -%}
        {{ target.schema }}_{{ custom_schema_name | trim }}
    {%- elif node.resource_type == 'seed' -%}
        staging
    {%- else -%}
        {{ target.schema }}
    {%- endif -%}
{%- endmacro %}
