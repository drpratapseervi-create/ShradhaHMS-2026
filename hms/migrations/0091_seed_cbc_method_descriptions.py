from django.db import migrations

# name -> method_description. Grouped by how the analyte is actually produced on a
# standard automated hematology analyzer; sanity-check against Shradha's own
# analyzer/reagent documentation before treating this as final, same caution as
# the LFT reference ranges.
METHOD_DESCRIPTIONS = {
    "Hemoglobin (Hb)": "Cyanmethemoglobin / colorimetric method",
    "Total Leukocyte Count (TLC)": "Automated cell counter (impedance/flow cytometry)",
    "Neutrophils": "Automated cell counter, flow cytometry / impedance differential",
    "Lymphocytes": "Automated cell counter, flow cytometry / impedance differential",
    "Eosinophils": "Automated cell counter, flow cytometry / impedance differential",
    "Monocytes": "Automated cell counter, flow cytometry / impedance differential",
    "Basophils": "Automated cell counter, flow cytometry / impedance differential",
    "Platelet Count": "Automated cell counter, impedance method",
    "RBC Count": "Automated cell counter, impedance method",
    "Hematocrit (PCV)": "Automated calculation from RBC indices",
    "MCV": "Calculated from RBC, Hb, and Hematocrit values",
    "MCH": "Calculated from RBC, Hb, and Hematocrit values",
    "MCHC": "Calculated from RBC, Hb, and Hematocrit values",
}


def seed_method_descriptions(apps, schema_editor):
    Investigation = apps.get_model("hms", "Investigation")
    InvestigationParameter = apps.get_model("hms", "InvestigationParameter")

    cbc = Investigation.objects.filter(name="CBC").first()
    if not cbc:
        return

    for name, description in METHOD_DESCRIPTIONS.items():
        InvestigationParameter.objects.filter(
            investigation=cbc, name=name, method_description=""
        ).update(method_description=description)


def remove_method_descriptions(apps, schema_editor):
    Investigation = apps.get_model("hms", "Investigation")
    InvestigationParameter = apps.get_model("hms", "InvestigationParameter")

    cbc = Investigation.objects.filter(name="CBC").first()
    if not cbc:
        return

    for name, description in METHOD_DESCRIPTIONS.items():
        InvestigationParameter.objects.filter(
            investigation=cbc, name=name, method_description=description
        ).update(method_description="")


class Migration(migrations.Migration):

    dependencies = [
        ("hms", "0090_seed_lft_creatinine_esr_parameters"),
    ]

    operations = [
        migrations.RunPython(seed_method_descriptions, remove_method_descriptions),
    ]
