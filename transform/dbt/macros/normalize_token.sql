{#- Fold a text expression so that "Café", "café" and "cafe" compare equal:
    lowercase, then map accented Latin letters to their base letter. Snowflake
    has no Unicode normalisation, so this is a translate() table. The same macro
    folds message tokens and stopword seeds, which keeps both sides symmetric. -#}
{% macro normalize_token(expression) -%}
    translate(
        lower({{ expression }}),
        'áàâãäåçéèêëíìîïñóòôõöúùûüýÿ',
        'aaaaaaceeeeiiiinooooouuuuyy'
    )
{%- endmacro %}
