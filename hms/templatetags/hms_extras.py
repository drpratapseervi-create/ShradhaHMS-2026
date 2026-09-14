import re

from django import template

register = template.Library()

_LEADING_NUMBER_RE = re.compile(r"^\s*\d+[\.\)]\s*")


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def comma_split(value):
    """Split a comma-separated string into a list of trimmed, non-empty parts.

    Strips any manually-typed leading number ("1.", "2)") from each part so
    older free-typed impressions don't get double-numbered on top of the
    auto-generated list numbering.
    """
    if not value:
        return []
    parts = [v.strip() for v in value.split(",") if v.strip()]
    return [_LEADING_NUMBER_RE.sub("", p).strip() for p in parts]