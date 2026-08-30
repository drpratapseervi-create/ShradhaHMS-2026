from django.db import migrations

# investigation_name -> (group, [ (name, unit, min_value, max_value, male_range,
#                                  female_range, loinc_code, loinc_display), ... ])
#
# AST/ALT/ALP are kept unisex for now (not split by sex) — sex-specific flagging
# is a combined follow-up across all tests, not per-test, per 2026-08-30 decision.
PARAMETERS_BY_INVESTIGATION = {
    "S. creatinine": ("Biochemistry", [
        ("Serum Creatinine", "mg/dL", 0.6, 1.3, "0.7-1.3", "0.6-1.1",
         "2160-0", "Creatinine [Mass/volume] in Serum or Plasma"),
    ]),
    "ESR": ("Hematology", [
        ("ESR (Westergren)", "mm/hr", 0, 20, "0-15", "0-20",
         "4537-7", "Erythrocyte [Sedimentation Rate] in Blood by Westergren method"),
    ]),
    "LFT": ("Biochemistry", [
        ("Total Bilirubin", "mg/dL", 0.3, 1.2, "", "",
         "1975-2", "Bilirubin.total [Mass/volume] in Serum or Plasma"),
        ("Direct (Conjugated) Bilirubin", "mg/dL", 0.0, 0.3, "", "",
         "1968-7", "Bilirubin.direct [Mass/volume] in Serum or Plasma"),
        ("Indirect Bilirubin", "mg/dL", 0.2, 0.8, "", "",
         "1971-1", "Bilirubin.indirect [Mass/volume] in Serum or Plasma"),
        ("SGOT (AST)", "U/L", 5, 40, "", "",
         "1920-8", "Aspartate aminotransferase [Enzymatic activity/volume] in Serum or Plasma"),
        ("SGPT (ALT)", "U/L", 5, 40, "", "",
         "1742-6", "Alanine aminotransferase [Enzymatic activity/volume] in Serum or Plasma"),
        ("Alkaline Phosphatase (ALP)", "U/L", 44, 147, "", "",
         "6768-6", "Alkaline phosphatase [Enzymatic activity/volume] in Serum or Plasma"),
        ("Total Protein", "g/dL", 6.0, 8.3, "", "",
         "2885-2", "Protein [Mass/volume] in Serum or Plasma"),
        ("Albumin", "g/dL", 3.5, 5.0, "", "",
         "1751-7", "Albumin [Mass/volume] in Serum or Plasma"),
        ("Globulin", "g/dL", 2.0, 3.5, "", "",
         "10834-0", "Globulin [Mass/volume] in Serum by calculation"),
        ("A/G Ratio", "", 1.0, 2.5, "", "",
         "1759-0", "Albumin/Globulin [Mass Ratio] in Serum or Plasma"),
    ]),
}


def seed_parameters(apps, schema_editor):
    Investigation = apps.get_model("hms", "Investigation")
    InvestigationParameter = apps.get_model("hms", "InvestigationParameter")

    for inv_name, (group, params) in PARAMETERS_BY_INVESTIGATION.items():
        inv = Investigation.objects.filter(name=inv_name).first()
        if not inv:
            continue
        for order, (name, unit, min_value, max_value, male_range, female_range,
                    loinc_code, loinc_display) in enumerate(params, start=1):
            InvestigationParameter.objects.get_or_create(
                investigation=inv,
                name=name,
                defaults={
                    "unit": unit,
                    "min_value": min_value,
                    "max_value": max_value,
                    "male_range": male_range,
                    "female_range": female_range,
                    "loinc_code": loinc_code,
                    "loinc_display": loinc_display,
                    "result_type": "numeric",
                    "group": group,
                    "order": order,
                    "show_in_report": True,
                },
            )


def remove_parameters(apps, schema_editor):
    Investigation = apps.get_model("hms", "Investigation")
    InvestigationParameter = apps.get_model("hms", "InvestigationParameter")

    for inv_name, (_group, params) in PARAMETERS_BY_INVESTIGATION.items():
        inv = Investigation.objects.filter(name=inv_name).first()
        if not inv:
            continue
        names = [row[0] for row in params]
        InvestigationParameter.objects.filter(investigation=inv, name__in=names).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("hms", "0089_seed_cbc_parameters"),
    ]

    operations = [
        migrations.RunPython(seed_parameters, remove_parameters),
    ]
