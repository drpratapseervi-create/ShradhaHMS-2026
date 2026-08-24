from django.db import migrations

VILLAGES = [
    "Aangdosh", "Auwa", "Badrajune", "Bala", "Bhangeshar", "Bhindar",
    "Bhanwari", "Chenda", "Chirpatiya", "Denda", "Dewali", "Dhola",
    "Dingai", "Gundoj", "Jadan", "Jojawar", "Kharda", "Khiwda", "Kurna",
    "Marwar", "Nadol", "Nimbali", "Pipliya", "Rana", "Ranawas", "Rani",
    "Sijat", "Sodawas", "Someshaar", "Sonai Maji",
]


def seed_villages(apps, schema_editor):
    VillageMaster = apps.get_model("hms", "VillageMaster")
    for name in VILLAGES:
        VillageMaster.objects.get_or_create(name=name)


def remove_villages(apps, schema_editor):
    VillageMaster = apps.get_model("hms", "VillageMaster")
    VillageMaster.objects.filter(name__in=VILLAGES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("hms", "0078_villagemaster"),
    ]

    operations = [
        migrations.RunPython(seed_villages, remove_villages),
    ]
