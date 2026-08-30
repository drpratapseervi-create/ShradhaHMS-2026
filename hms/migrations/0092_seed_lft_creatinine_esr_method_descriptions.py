from django.db import migrations

# investigation_name -> { parameter_name: method_description }. These are standard
# textbook clinical-chemistry methods (IFCC kinetic assays, diazo/biuret/BCG
# colorimetry, Jaffe's for creatinine) rather than analyzer-specific text — sanity
# check against Shradha's own analyzer/reagent documentation before treating this
# as final, same caution as the CBC method descriptions and the LFT ranges.
METHOD_DESCRIPTIONS_BY_INVESTIGATION = {
    "S. creatinine": {
        "Serum Creatinine": "Modified Jaffe's kinetic (alkaline picrate) method",
    },
    "ESR": {
        "ESR (Westergren)": "Westergren method (mm fall in 1 hour)",
    },
    "LFT": {
        "Total Bilirubin": "Diazo method (colorimetric)",
        "Direct (Conjugated) Bilirubin": "Diazo method (colorimetric)",
        "Indirect Bilirubin": "Calculated (Total minus Direct Bilirubin)",
        "SGOT (AST)": "IFCC kinetic method (without pyridoxal phosphate)",
        "SGPT (ALT)": "IFCC kinetic method (without pyridoxal phosphate)",
        "Alkaline Phosphatase (ALP)": "IFCC/DGKC kinetic method (p-nitrophenyl phosphate substrate)",
        "Total Protein": "Biuret method (colorimetric)",
        "Albumin": "Bromocresol Green (BCG) dye-binding method",
        "Globulin": "Calculated (Total Protein minus Albumin)",
        "A/G Ratio": "Calculated (Albumin divided by Globulin)",
    },
}


def seed_method_descriptions(apps, schema_editor):
    Investigation = apps.get_model("hms", "Investigation")
    InvestigationParameter = apps.get_model("hms", "InvestigationParameter")

    for inv_name, descriptions in METHOD_DESCRIPTIONS_BY_INVESTIGATION.items():
        inv = Investigation.objects.filter(name=inv_name).first()
        if not inv:
            continue
        for name, description in descriptions.items():
            InvestigationParameter.objects.filter(
                investigation=inv, name=name, method_description=""
            ).update(method_description=description)


def remove_method_descriptions(apps, schema_editor):
    Investigation = apps.get_model("hms", "Investigation")
    InvestigationParameter = apps.get_model("hms", "InvestigationParameter")

    for inv_name, descriptions in METHOD_DESCRIPTIONS_BY_INVESTIGATION.items():
        inv = Investigation.objects.filter(name=inv_name).first()
        if not inv:
            continue
        for name, description in descriptions.items():
            InvestigationParameter.objects.filter(
                investigation=inv, name=name, method_description=description
            ).update(method_description="")


class Migration(migrations.Migration):

    dependencies = [
        ("hms", "0091_seed_cbc_method_descriptions"),
    ]

    operations = [
        migrations.RunPython(seed_method_descriptions, remove_method_descriptions),
    ]
