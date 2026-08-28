from django.db import migrations


def forwards(apps, schema_editor):
    Investigation = apps.get_model("hms", "Investigation")
    Investigation.objects.filter(name="Chest X Ray").update(name="Chest X-Ray")


def backwards(apps, schema_editor):
    Investigation = apps.get_model("hms", "Investigation")
    Investigation.objects.filter(name="Chest X-Ray").update(name="Chest X Ray")


class Migration(migrations.Migration):

    dependencies = [
        ("hms", "0084_collapse_investigation_categories"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
