from django.db import migrations

ADVICE_OPTIONS = [
    "No heavy lifting",
    "Avoid alcohol",
    "Avoid smoking",
    "Walk 30 min daily",
    "Monitor BP daily",
    "Monitor sugar daily",
    "Keep wound dry",
    "Dressing daily",
]

DIET_OPTIONS = [
    "Normal diet",
    "Soft diet",
    "Liquid diet",
    "Diabetic diet",
    "Low salt diet",
    "High protein diet",
]


def seed_options(apps, schema_editor):
    AdviceOption = apps.get_model("hms", "AdviceOption")
    DietAdviceOption = apps.get_model("hms", "DietAdviceOption")
    for i, text in enumerate(ADVICE_OPTIONS):
        AdviceOption.objects.get_or_create(text=text, defaults={"is_active": True, "sort_order": i})
    for i, text in enumerate(DIET_OPTIONS):
        DietAdviceOption.objects.get_or_create(text=text, defaults={"is_active": True, "sort_order": i})


def remove_options(apps, schema_editor):
    AdviceOption = apps.get_model("hms", "AdviceOption")
    DietAdviceOption = apps.get_model("hms", "DietAdviceOption")
    AdviceOption.objects.filter(text__in=ADVICE_OPTIONS).delete()
    DietAdviceOption.objects.filter(text__in=DIET_OPTIONS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("hms", "0072_adviceoption_dietadviceoption"),
    ]

    operations = [
        migrations.RunPython(seed_options, remove_options),
    ]
