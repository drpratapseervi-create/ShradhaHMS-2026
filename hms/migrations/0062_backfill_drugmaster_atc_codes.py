from django.db import migrations

# Manually verified against the WHO ATC/DDD Index (https://www.whocc.no/atc_ddd_index/).
# Only rows we're confident about a single, unambiguous WHO code for are
# included here — multi-ingredient OTC combinations with no official
# WHO-assigned combo code, or rows whose generic_name field just repeats
# the brand name, are deliberately left out rather than guessed.
ATC_BY_NAME = {
    "Cap.Lumia 60K":   "A11CC05",  # Colecalciferol (Vitamin D3)
    "Tab. Flunarin":   "N07CA03",  # Flunarizine
    "TTab. Telvas-AM": "C09DB04",  # Telmisartan + Amlodipine
    "Tab. Shelcal XT": "A12AX",    # Calcium, combinations with vitamin D
    "Tab.Shelcal":     "A12AX",    # Calcium, combinations with vitamin D
}


def fill_atc_codes(apps, schema_editor):
    DrugMaster = apps.get_model('hms', 'DrugMaster')
    for name, code in ATC_BY_NAME.items():
        DrugMaster.objects.filter(name=name, atc_code__in=['', None]).update(atc_code=code)


def unfill_atc_codes(apps, schema_editor):
    DrugMaster = apps.get_model('hms', 'DrugMaster')
    DrugMaster.objects.filter(name__in=ATC_BY_NAME.keys(), atc_code__in=ATC_BY_NAME.values()).update(atc_code='')


class Migration(migrations.Migration):

    dependencies = [
        ('hms', '0061_atc_code_validation_and_nullable'),
    ]

    operations = [
        migrations.RunPython(fill_atc_codes, unfill_atc_codes),
    ]
