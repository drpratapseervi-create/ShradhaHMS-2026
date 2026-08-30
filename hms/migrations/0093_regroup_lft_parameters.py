from django.db import migrations

# name -> sub-panel group. Regroups the flat "Biochemistry" LFT panel into three
# clinically grouped sections (Bilirubin Metabolism / Hepatic Enzyme / Serum
# Protein) for the print report — the print template already renders one
# section per distinct InvestigationParameter.group value, in parameter order,
# so this is a data-only change.
LFT_GROUPS = {
    "Total Bilirubin": "Bilirubin Metabolism Panel",
    "Direct (Conjugated) Bilirubin": "Bilirubin Metabolism Panel",
    "Indirect Bilirubin": "Bilirubin Metabolism Panel",
    "SGOT (AST)": "Hepatic Enzyme Profile",
    "SGPT (ALT)": "Hepatic Enzyme Profile",
    "Alkaline Phosphatase (ALP)": "Hepatic Enzyme Profile",
    "Total Protein": "Serum Protein Fractionation",
    "Albumin": "Serum Protein Fractionation",
    "Globulin": "Serum Protein Fractionation",
    "A/G Ratio": "Serum Protein Fractionation",
}

PREVIOUS_GROUP = "Biochemistry"


def regroup_lft(apps, schema_editor):
    Investigation = apps.get_model("hms", "Investigation")
    InvestigationParameter = apps.get_model("hms", "InvestigationParameter")

    lft = Investigation.objects.filter(name="LFT").first()
    if not lft:
        return

    for name, group in LFT_GROUPS.items():
        InvestigationParameter.objects.filter(investigation=lft, name=name).update(group=group)


def revert_lft_grouping(apps, schema_editor):
    Investigation = apps.get_model("hms", "Investigation")
    InvestigationParameter = apps.get_model("hms", "InvestigationParameter")

    lft = Investigation.objects.filter(name="LFT").first()
    if not lft:
        return

    InvestigationParameter.objects.filter(
        investigation=lft, name__in=LFT_GROUPS.keys()
    ).update(group=PREVIOUS_GROUP)


class Migration(migrations.Migration):

    dependencies = [
        ("hms", "0092_seed_lft_creatinine_esr_method_descriptions"),
    ]

    operations = [
        migrations.RunPython(regroup_lft, revert_lft_grouping),
    ]
