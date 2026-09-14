from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def comma_split(value):
    """Split a comma-separated string into a list of trimmed, non-empty parts."""
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]