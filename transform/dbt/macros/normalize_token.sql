{#- Fold a text expression so that "Café", "café" and "cafe" compare equal:
    lowercase, decompose accents (NFD) and strip combining marks (\p{Mn}).
    The same macro folds message tokens and stopword seeds. -#}
{% macro normalize_token(expression) -%}
    replaceRegexpAll(normalizeUTF8NFD(lowerUTF8({{ expression }})), '\\p{Mn}', '')
{%- endmacro %}
