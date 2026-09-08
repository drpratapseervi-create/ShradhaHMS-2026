from django.db import migrations

FOLLOWUP_PHRASES = [
    "USG after 10 days",
    "Admission and patient refused",
    "Biopsy report",
]


def seed_phrases(apps, schema_editor):
    FollowUpNotePhrase = apps.get_model("hms", "FollowUpNotePhrase")
    for i, text in enumerate(FOLLOWUP_PHRASES):
        FollowUpNotePhrase.objects.get_or_create(text=text, defaults={"is_active": True, "sort_order": i})


def remove_phrases(apps, schema_editor):
    FollowUpNotePhrase = apps.get_model("hms", "FollowUpNotePhrase")
    FollowUpNotePhrase.objects.filter(text__in=FOLLOWUP_PHRASES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("hms", "0100_followupnotephrase"),
    ]

    operations = [
        migrations.RunPython(seed_phrases, remove_phrases),
    ]
