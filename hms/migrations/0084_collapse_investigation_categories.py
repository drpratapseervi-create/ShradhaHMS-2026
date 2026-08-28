from django.db import migrations


# One canonical InvestigationCategory per department code.
CANONICAL = {
    "BIOCHEMISTRY": "Biochemistry",
    "HEMATOLOGY":   "Hematology",
    "MICROBIOLOGY": "Microbiology",
    "RADIOLOGY":    "Radiology",
    "CARDIOLOGY":   "Cardiology",
}


def forwards(apps, schema_editor):
    """Collapse the flat 'one category per test' rows into one category per
    department. Purely a data move: Investigation.category is re-pointed, the
    now-empty leftover categories are deleted. dept_code is preserved on the
    keeper, so every report/query that groups by dept_code is unaffected."""
    Category = apps.get_model("hms", "InvestigationCategory")
    Investigation = apps.get_model("hms", "Investigation")

    for dept_code, canonical_name in CANONICAL.items():
        cats = list(Category.objects.filter(dept_code=dept_code).order_by("id"))
        if not cats:
            continue

        # Prefer a category already named canonically (e.g. "Cardiology" from
        # 0083); otherwise take the lowest-id one and rename it.
        keeper = next((c for c in cats if c.name == canonical_name), cats[0])
        if keeper.name != canonical_name:
            keeper.name = canonical_name
            keeper.save(update_fields=["name"])

        # Re-parent every investigation in this department onto the keeper.
        Investigation.objects.filter(category__dept_code=dept_code) \
            .exclude(category_id=keeper.id) \
            .update(category_id=keeper.id)

        # Safety: nothing may still hang off a leftover category before we drop
        # it (Investigation.category is CASCADE — a stray row would take its
        # bill items with it).
        leftovers = Category.objects.filter(dept_code=dept_code).exclude(id=keeper.id)
        stranded = Investigation.objects.filter(category__in=leftovers).count()
        if stranded:
            raise RuntimeError(
                f"0084: {stranded} investigation(s) still on leftover "
                f"{dept_code} categories after re-parent — aborting."
            )
        leftovers.delete()


def backwards(apps, schema_editor):
    """Restore the flat 'one category per test' layout (the Phase-1 end state).
    New category ids are assigned; each new category is named after its test."""
    Category = apps.get_model("hms", "InvestigationCategory")
    Investigation = apps.get_model("hms", "Investigation")

    for inv in Investigation.objects.select_related("category").all():
        dept_code = inv.category.dept_code
        new_cat = Category.objects.create(name=inv.name, dept_code=dept_code)
        inv.category_id = new_cat.id
        inv.save(update_fields=["category"])

    # Drop the canonical categories that are now empty.
    for dept_code, canonical_name in CANONICAL.items():
        Category.objects.filter(
            dept_code=dept_code, name=canonical_name, investigation__isnull=True
        ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("hms", "0083_standardize_investigations"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
