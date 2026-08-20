from django.db import migrations

PAST_HISTORY = [
    "Diabetes Mellitus",
    "HTN",
    "Hypothyroidism",
    "IHD",
    "COPD",
]

SURGICAL_HISTORY = [
    "Lap Appendectomy",
    "Lap Cholecystectomy",
    "Inguinal Hernia Repair",
    "Umbilical Hernia",
]


def seed_history(apps, schema_editor):
    PastHistory = apps.get_model("hms", "PastHistory")
    SurgicalHistory = apps.get_model("hms", "SurgicalHistory")
    for name in PAST_HISTORY:
        PastHistory.objects.get_or_create(name=name, defaults={"is_active": True})
    for name in SURGICAL_HISTORY:
        SurgicalHistory.objects.get_or_create(name=name, defaults={"is_active": True})


def remove_history(apps, schema_editor):
    PastHistory = apps.get_model("hms", "PastHistory")
    SurgicalHistory = apps.get_model("hms", "SurgicalHistory")
    PastHistory.objects.filter(name__in=PAST_HISTORY).delete()
    SurgicalHistory.objects.filter(name__in=SURGICAL_HISTORY).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("hms", "0068_pasthistory_surgicalhistory_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_history, remove_history),
    ]
