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
# Per-line, not per-text — matched against one line at a time (see
# usg_findings_line_parts below), so no (?m) flag needed here.
_USG_LABEL_LINE_RE = re.compile(
    r"^(" + "|".join(re.escape(l) for l in _USG_ORGAN_LABELS) + r"):(.*)$"
)

_usg_known_narrative_lines_cache = None


def _usg_known_narrative_lines():
    """Every line that appears verbatim in one of the standard USG findings
    templates, across every scan type/gender variant — used to tell a fixed
    boilerplate line with no organ label (e.g. "Colon wall thickness...")
    apart from a line the doctor typed in by hand, which has neither."""
    global _usg_known_narrative_lines_cache
    if _usg_known_narrative_lines_cache is None:
        from ..models import USGReport
        lines = set()
        for template in USGReport.FINDINGS_TEMPLATES.values():
            variants = template.values() if isinstance(template, dict) else [template]
            for text in variants:
                for line in (text or "").split("\n"):
                    line = line.strip()
                    if line:
                        lines.add(line)
        _usg_known_narrative_lines_cache = lines
    return _usg_known_narrative_lines_cache


def usg_findings_line_parts(line):
    """Classify one line of USG findings_text for bold rendering. Returns a
    list of (is_bold, text) segments to render in order:
    - a recognized organ label ("Liver:") — label bold, rest of the line normal
    - a known fixed boilerplate line with no label — normal
    - anything else (manually typed/added, e.g. "5 mm calculus in left
      kidney") — the whole line bold, so custom additions stand out same as
      an organ header."""
    stripped = line.strip()
    if not stripped or stripped == "-":
        return [(False, line)]
    m = _USG_LABEL_LINE_RE.match(line)
    if m:
        return [(True, m.group(1) + ":"), (False, m.group(2))]
    if stripped in _usg_known_narrative_lines():
        return [(False, line)]
    return [(True, line)]


@register.filter
def bold_usg_labels(value):
    """Renders USG findings_text with organ labels and manually-added lines
    in <strong>, standard narrative sentences left normal weight. Escapes
    all text itself and returns marked-safe HTML (with the original "\\n"s
    preserved) for `linebreaksbr` to turn into <br> afterward."""
    if not value:
        return value
    out_lines = []
    for line in value.replace("\r\n", "\n").split("\n"):
        rendered = "".join(
            f"<strong>{escape(text)}</strong>" if bold else escape(text)
            for bold, text in usg_findings_line_parts(line)
        )
        out_lines.append(rendered)
    return mark_safe("\n".join(out_lines))


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