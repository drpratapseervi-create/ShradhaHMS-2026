from django.db import migrations, models


# ---------------------------------------------------------------------------
# LFT price — agreed with Dr. Pratap. MUST be set before running `migrate`;
# forwards() aborts loudly if it is left as None.
# ---------------------------------------------------------------------------
LFT_PRICE = 600  # agreed with Dr. Pratap, 2026-08-28


def forwards(apps, schema_editor):
    Investigation = apps.get_model("hms", "Investigation")
    InvestigationCategory = apps.get_model("hms", "InvestigationCategory")

    if LFT_PRICE is None:
        raise RuntimeError(
            "0083_standardize_investigations: LFT_PRICE is not set. "
            "Edit this migration, set LFT_PRICE to the agreed amount, then run migrate."
        )

    # 1. Fix the medical-abbreviation typo on the test itself (ERS -> ESR).
    #    Filtered by name (not pk) so it is safe on any environment. The FK id
    #    is untouched: the 18 InvestigationBillItem rows and 18
    #    Consultation.investigations M2M rows keep pointing at the same row.
    Investigation.objects.filter(name="ERS").update(name="ESR")

    # 2. Promote the single-test "ECG" category into a real department,
    #    "Cardiology". Only the category row changes; Investigation "ECG"
    #    stays inside it (category_id unchanged), so its 12 bill items and
    #    11 M2M rows are unaffected. dept_code flips ECG -> CARDIOLOGY so the
    #    daily report now buckets this revenue under the Cardiology line.
    InvestigationCategory.objects.filter(name="ECG", dept_code="ECG").update(
        name="Cardiology", dept_code="CARDIOLOGY"
    )

    # 3. Add the missing LFT test under the existing (currently empty)
    #    "LFT" Biochemistry category.
    lft_cat = InvestigationCategory.objects.filter(
        name="LFT", dept_code="BIOCHEMISTRY"
    ).first()
    if lft_cat:
        Investigation.objects.get_or_create(
            category=lft_cat,
            name="LFT",
            defaults={"price": LFT_PRICE, "is_active": True},
        )


def backwards(apps, schema_editor):
    Investigation = apps.get_model("hms", "Investigation")
    InvestigationCategory = apps.get_model("hms", "InvestigationCategory")
    InvestigationBillItem = apps.get_model("hms", "InvestigationBillItem")

    InvestigationCategory.objects.filter(
        name="Cardiology", dept_code="CARDIOLOGY"
    ).update(name="ECG", dept_code="ECG")

    Investigation.objects.filter(name="ESR").update(name="ERS")

    # Drop the LFT test only if nothing references it yet.
    used = set(
        InvestigationBillItem.objects.values_list("investigation_id", flat=True)
    )
    (
        Investigation.objects.filter(name="LFT", category__name="LFT")
        .exclude(id__in=used)
        .delete()
    )


class Migration(migrations.Migration):

    dependencies = [
        ("hms", "0082_consultation_ai_investigation_input_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="investigationcategory",
            name="dept_code",
            field=models.CharField(
                choices=[
                    ("RADIOLOGY", "Radiology"),
                    ("HISTOPATHOLOGY", "Histopathology"),
                    ("BIOCHEMISTRY", "Biochemistry"),
                    ("HEMATOLOGY", "Hematology"),
                    ("MICROBIOLOGY", "Microbiology"),
                    ("CARDIOLOGY", "Cardiology"),
                    ("ECG", "ECG"),
                    ("ENDOSCOPY", "Endoscopy & Procedures"),
                    ("OTHER", "Other"),
                ],
                default="OTHER",
                help_text="Used in reports for department-wise billing summary.",
                max_length=20,
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
