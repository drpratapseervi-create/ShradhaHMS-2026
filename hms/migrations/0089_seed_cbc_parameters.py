from django.db import migrations

# name, unit, min_value, max_value, male_range, female_range, loinc_code, loinc_display
# male_range/female_range are only set where they differ from each other; when both
# sexes share one range, min_value/max_value alone drive both display and flagging.
CBC_PARAMETERS = [
    ("Hemoglobin (Hb)", "g/dL", 12.0, 17.0, "13.0-17.0", "12.0-15.5",
     "718-7", "Hemoglobin [Mass/volume] in Blood"),
    ("Total Leukocyte Count (TLC)", "/µL", 4000, 11000, "", "",
     "6690-2", "Leukocytes [#/volume] in Blood by Automated count"),
    ("Neutrophils", "%", 40, 70, "", "",
     "770-8", "Neutrophils/100 leukocytes in Blood by Automated count"),
    ("Lymphocytes", "%", 20, 40, "", "",
     "736-9", "Lymphocytes/100 leukocytes in Blood by Automated count"),
    ("Eosinophils", "%", 1, 6, "", "",
     "713-8", "Eosinophils/100 leukocytes in Blood by Automated count"),
    ("Monocytes", "%", 2, 8, "", "",
     "5905-5", "Monocytes/100 leukocytes in Blood by Automated count"),
    ("Basophils", "%", 0, 1, "", "",
     "706-2", "Basophils/100 leukocytes in Blood by Automated count"),
    ("Platelet Count", "/µL", 150000, 410000, "", "",
     "777-3", "Platelets [#/volume] in Blood by Automated count"),
    ("RBC Count", "million/µL", 4.0, 5.5, "4.5-5.5", "4.0-5.0",
     "789-8", "Erythrocytes [#/volume] in Blood by Automated count"),
    ("Hematocrit (PCV)", "%", 36, 50, "40-50", "36-44",
     "4544-3", "Hematocrit [Volume Fraction] of Blood by Automated count"),
    ("MCV", "fL", 83, 101, "", "",
     "787-2", "MCV [Entitic mean volume] in Red Blood Cells by Automated count"),
    ("MCH", "pg", 27, 32, "", "",
     "785-6", "MCH [Entitic mass] by Automated count"),
    ("MCHC", "g/dL", 31.5, 34.5, "", "",
     "786-4", "MCHC [Entitic Mass/volume] in Red Blood Cells by Automated count"),
]


def seed_cbc_parameters(apps, schema_editor):
    Investigation = apps.get_model("hms", "Investigation")
    InvestigationParameter = apps.get_model("hms", "InvestigationParameter")

    cbc = Investigation.objects.filter(name="CBC").first()
    if not cbc:
        return

    for order, (name, unit, min_value, max_value, male_range, female_range,
                loinc_code, loinc_display) in enumerate(CBC_PARAMETERS, start=1):
        InvestigationParameter.objects.get_or_create(
            investigation=cbc,
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
                "group": "Hematology",
                "order": order,
                "show_in_report": True,
            },
        )


def remove_cbc_parameters(apps, schema_editor):
    Investigation = apps.get_model("hms", "Investigation")
    InvestigationParameter = apps.get_model("hms", "InvestigationParameter")

    cbc = Investigation.objects.filter(name="CBC").first()
    if not cbc:
        return

    names = [row[0] for row in CBC_PARAMETERS]
    InvestigationParameter.objects.filter(investigation=cbc, name__in=names).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("hms", "0088_investigationparameter_method_description"),
    ]

    operations = [
        migrations.RunPython(seed_cbc_parameters, remove_cbc_parameters),
    ]
