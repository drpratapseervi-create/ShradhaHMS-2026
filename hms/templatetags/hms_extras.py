import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

_LEADING_NUMBER_RE = re.compile(r"^\s*\d+[\.\)]\s*")

# Organ labels in the USG standard findings templates (hms/models/imaging.py)
# that should print bold as inline headers, while the narrative sentence
# after each stays normal weight — whether it's the original template
# wording or something the doctor typed/edited in.
_USG_ORGAN_LABELS = [
    "Liver", "Portal Vein", "Gallbladder", "CBD", "Pancreas", "Spleen",
    "Kidneys", "Right Kidney", "Left Kidney", "Bladder",
    "Uterus and Ovaries", "Prostate",
]
_USG_LABEL_RE = re.compile(
    r"(?m)^(" + "|".join(re.escape(l) for l in _USG_ORGAN_LABELS) + r"):"
)


@register.filter
def bold_usg_labels(value):
    """Wrap known organ-name labels (start of line, e.g. "Liver:") in <strong>
    so they read as inline headers when printed — everything else in the
    text stays normal weight. Escapes the rest of the text itself since this
    returns pre-rendered HTML (marked safe) for `linebreaksbr` to follow."""
    if not value:
        return value
    return mark_safe(_USG_LABEL_RE.sub(r"<strong>\1:</strong>", escape(value)))


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