from django.db import migrations

EMERGENCY_INSTRUCTIONS = (
    "In case of complaints of fever, abdomen pain, vomiting, headache "
    "immediate contact to hospital emergency No:- 94141-22542"
)
STANDARD_FOLLOW_UP = "Will follow up in surgery OPD at 10:00 AM."

TEMPLATES = [
    dict(
        procedure_name="Lap Appendectomy", gender="M",
        diagnosis="Acute Appendicitis",
        chief_complaints="Pain abdomen x 5 days",
        general_examination="Middle aged patient, conscious, oriented. Pulse: 100/min, Blood pressure: 100/80 mm of Hg, no pallor, no pedal edema.",
        local_examination="Soft, tenderness present in RIF, bowel sound present.",
        operation_notes="He underwent laparoscopic appendectomy under general anaesthesia.",
        course_in_hospital="Patient was admitted with diagnosis of acute appendicitis. He underwent laparoscopic appendectomy under spinal anaesthesia. Post operative he did well & is being discharged in satisfactory condition.",
        treatment_on_discharge="Soft diet.",
        advice="Soft diet.",
    ),
    dict(
        procedure_name="Lap Appendectomy", gender="F",
        diagnosis="Acute Appendicitis",
        chief_complaints="Pain abdomen x 2 months",
        general_examination="Middle aged patient, conscious, oriented. Pulse: 80/min, Blood pressure: 128/80 mm of Hg, no pallor, no pedal edema.",
        local_examination="Soft, tenderness present in RIF, bowel sound present.",
        operation_notes="She underwent laparoscopic appendectomy under spinal anaesthesia.",
        course_in_hospital="Patient was admitted with diagnosis of acute appendicitis and she underwent laparoscopic appendectomy under spinal anaesthesia. Post operative she did well & is being discharged in satisfactory condition.",
        treatment_on_discharge="Soft diet.",
        advice="Soft diet.",
    ),
    dict(
        procedure_name="Lap Cholecystectomy", gender="M",
        diagnosis="Cholelithiasis (Chronic)",
        chief_complaints="Pain abdomen x 2 months",
        general_examination="Middle aged patient, conscious, oriented. Pulse: 100/min, Blood pressure: 100/80 mm of Hg, no pallor, no pedal edema.",
        local_examination="Soft, non tender, bowel sound present.",
        operation_notes="He underwent laparoscopic cholecystectomy under general anaesthesia.",
        course_in_hospital="Patient was admitted with diagnosis of cholelithiasis and he underwent laparoscopic cholecystectomy under general anaesthesia. Post operative he did well & is being discharged in satisfactory condition.",
        treatment_on_discharge="",
        advice="",
    ),
    dict(
        procedure_name="Lap Cholecystectomy", gender="F",
        diagnosis="Chronic Calculus Cholecystitis",
        chief_complaints="Pain abdomen x 6 months",
        general_examination="Middle aged patient, conscious, oriented. Pulse: 90/min, Blood pressure: 110/80 mm of Hg, no pallor, no pedal edema.",
        local_examination="Soft, non tender, bowel sound present.",
        operation_notes="She underwent laparoscopic cholecystectomy under general anaesthesia.",
        course_in_hospital="Patient was admitted with diagnosis of cholelithiasis and underwent laparoscopic cholecystectomy under general anaesthesia. Post operative she did well & is being discharged in satisfactory condition.",
        treatment_on_discharge="Soft diet.",
        advice="Soft diet.",
    ),
    dict(
        procedure_name="Hydrocelectomy - Left", gender="M",
        diagnosis="Hydrocele (Left side)",
        chief_complaints="Scrotal swelling & pain, left side x 2 years",
        general_examination="Patient, conscious, oriented. Pulse: 90/min, Blood pressure: 140/80 mm of Hg, no pallor, no pedal edema.",
        local_examination="Abdomen soft, left side scrotal swelling noted.",
        operation_notes="He underwent left side hydrocelectomy under spinal anaesthesia.",
        course_in_hospital="Patient was admitted with diagnosis of left hydrocele and underwent left side hydrocelectomy under spinal anaesthesia. Post operative he did well & is being discharged in satisfactory condition.",
        treatment_on_discharge="Scrotal support.",
        advice="Scrotal support.",
    ),
    dict(
        procedure_name="Hydrocelectomy - Right", gender="M",
        diagnosis="Hydrocele (Right side)",
        chief_complaints="Scrotal swelling & pain, right side x 2 years",
        general_examination="Patient, conscious, oriented. Pulse: 90/min, Blood pressure: 110/80 mm of Hg, no pallor, no pedal edema.",
        local_examination="Abdomen soft, right side scrotal swelling noted.",
        operation_notes="He underwent right side hydrocelectomy under spinal anaesthesia.",
        course_in_hospital="Patient was admitted with diagnosis of right hydrocele and underwent right side hydrocelectomy under spinal anaesthesia. Post operative he did well & is being discharged in satisfactory condition.",
        treatment_on_discharge="Scrotal support.",
        advice="Scrotal support.",
    ),
    dict(
        procedure_name="Mesh Herniaplasty - Left", gender="M",
        diagnosis="Left Inguinal Hernia (Direct)",
        chief_complaints="Inguinal swelling & pain, left side x 4 months",
        general_examination="Middle aged patient, conscious, oriented. Pulse: 80/min, Blood pressure: 120/80 mm of Hg, no pallor, no pedal edema.",
        local_examination="Abdomen soft, left side inguinal & scrotal swelling present.",
        operation_notes="He underwent left inguinal mesh hernioplasty under spinal anaesthesia.",
        course_in_hospital="Patient was admitted with diagnosis of left inguinal hernia and underwent left inguinal mesh hernioplasty under spinal anaesthesia. Post operative he did well & is being discharged in satisfactory condition.",
        treatment_on_discharge="Avoid heavy weight lifting x 3 months.",
        advice="Avoid heavy weight lifting x 3 months.",
    ),
    dict(
        procedure_name="Mesh Herniaplasty - Right", gender="M",
        diagnosis="Inguinal Hernia (Right side)",
        chief_complaints="Inguinal swelling, right side x 10 months",
        general_examination="Middle aged patient, conscious, oriented. Pulse: 90/min, Blood pressure: 120/80 mm of Hg, no pallor, no pedal edema.",
        local_examination="Abdomen soft, right inguinal reducible swelling present.",
        operation_notes="He underwent right inguinal mesh hernioplasty under spinal anaesthesia.",
        course_in_hospital="Patient was admitted with diagnosis of inguinal hernia (right side) and underwent right inguinal mesh hernioplasty under spinal anaesthesia. Post operative he did well & is being discharged in satisfactory condition.",
        treatment_on_discharge="Avoid heavy lifting x 3 months.",
        advice="Avoid heavy lifting x 3 months.",
    ),
    dict(
        procedure_name="Herniotomy - Left", gender="M",
        diagnosis="Hernia (Left side)",
        chief_complaints="Inguinal swelling & pain, left side x 10-12 months",
        general_examination="Patient, conscious, oriented. Pulse: 90/min, Blood pressure: 100/80 mm of Hg, no pallor, no pedal edema.",
        local_examination="Abdomen soft, left side scrotal swelling present.",
        operation_notes="He underwent left side herniotomy under general anaesthesia.",
        course_in_hospital="Patient was admitted with diagnosis of left side hernia and underwent left side herniotomy under general anaesthesia. Post operative he did well & is being discharged in satisfactory condition.",
        treatment_on_discharge="Soft diet.",
        advice="Soft diet.",
    ),
    dict(
        procedure_name="Herniotomy - Right", gender="M",
        diagnosis="Hernia (Right side)",
        chief_complaints="Inguinal swelling & pain, right side x 10-12 months",
        general_examination="Patient, conscious, oriented. Pulse: 90/min, Blood pressure: 100/80 mm of Hg, no pallor, no pedal edema.",
        local_examination="Abdomen soft, right side scrotal swelling present.",
        operation_notes="He underwent right side herniotomy under general anaesthesia.",
        course_in_hospital="Patient was admitted with diagnosis of right side hernia and underwent right side herniotomy under general anaesthesia. Post operative he did well & is being discharged in satisfactory condition.",
        treatment_on_discharge="Soft diet.",
        advice="Soft diet.",
    ),
    dict(
        procedure_name="URS - Left", gender="M",
        diagnosis="Left Ureterolithiasis with Hydronephrosis",
        chief_complaints="Burning micturition x 6 months\nPain abdomen x 15 days",
        general_examination="Middle aged patient, conscious, oriented. Pulse: 80/min, Blood pressure: 120/80 mm of Hg, no pallor, no pedal edema.",
        local_examination="Soft, non tender, bowel sound present.",
        operation_notes="He underwent left side URSL with DJ stent placement under spinal anaesthesia.",
        course_in_hospital="Patient was admitted with diagnosis of ureterolithiasis with hydronephrosis and underwent left side URSL under spinal anaesthesia. Post operative he did well & is being discharged in satisfactory condition.",
        treatment_on_discharge="DJ stent removal follow-up.",
        advice="DJ stent removal follow-up.",
    ),
    dict(
        procedure_name="URS - Left", gender="F",
        diagnosis="Left Ureterolithiasis with Hydronephrosis",
        chief_complaints="Burning micturition x 6 months\nPain abdomen x 15 days",
        general_examination="Middle aged patient, conscious, oriented. Pulse: 80/min, Blood pressure: 120/80 mm of Hg, no pallor, no pedal edema.",
        local_examination="Soft, non tender, bowel sound present.",
        operation_notes="She underwent left side URSL with DJ stent placement under spinal anaesthesia.",
        course_in_hospital="Patient was admitted with diagnosis of ureterolithiasis with hydronephrosis and underwent left side URSL under spinal anaesthesia. Post operative she did well & is being discharged in satisfactory condition.",
        treatment_on_discharge="DJ stent removal follow-up.",
        advice="DJ stent removal follow-up.",
    ),
    dict(
        procedure_name="URS - Right", gender="M",
        diagnosis="Right Ureterolithiasis with Hydronephrosis",
        chief_complaints="Burning micturition x 6 months\nPain abdomen x 15 days",
        general_examination="Middle aged patient, conscious, oriented. Pulse: 80/min, Blood pressure: 120/80 mm of Hg, no pallor, no pedal edema.",
        local_examination="Soft, non tender, bowel sound present.",
        operation_notes="He underwent right side URSL with DJ stent placement under spinal anaesthesia.",
        course_in_hospital="Patient was admitted with diagnosis of ureterolithiasis with hydronephrosis and underwent right side URSL under spinal anaesthesia. Post operative he did well & is being discharged in satisfactory condition.",
        treatment_on_discharge="DJ stent removal follow-up.",
        advice="DJ stent removal follow-up.",
    ),
    dict(
        procedure_name="URS - Right", gender="F",
        diagnosis="Right Ureterolithiasis with Hydronephrosis",
        chief_complaints="Burning micturition x 6 months\nPain abdomen x 15 days",
        general_examination="Middle aged patient, conscious, oriented. Pulse: 80/min, Blood pressure: 120/80 mm of Hg, no pallor, no pedal edema.",
        local_examination="Soft, non tender, bowel sound present.",
        operation_notes="She underwent right side URSL with DJ stent placement under spinal anaesthesia.",
        course_in_hospital="Patient was admitted with diagnosis of ureterolithiasis with hydronephrosis and underwent right side URSL under spinal anaesthesia. Post operative she did well & is being discharged in satisfactory condition.",
        treatment_on_discharge="DJ stent removal follow-up.",
        advice="DJ stent removal follow-up.",
    ),
    dict(
        procedure_name="Breast Lumpectomy - Bilateral", gender="F",
        diagnosis="Bilateral Breast Lump",
        chief_complaints="Swelling in bilateral breast x 6 months",
        general_examination="Young patient, conscious, oriented. Pulse: 80/min, Blood pressure: 110/80 mm of Hg, pallor present, no pedal edema.",
        local_examination="Bilateral breast swelling noted.",
        operation_notes="She underwent bilateral breast lumpectomy under general anaesthesia.",
        course_in_hospital="Patient was admitted with diagnosis of bilateral breast lump and underwent bilateral breast lumpectomy under general anaesthesia. Post operative she did well & is being discharged in satisfactory condition.",
        treatment_on_discharge="Biopsy report follow-up.",
        advice="Biopsy report follow-up.",
    ),
    dict(
        procedure_name="Breast Lumpectomy - Right", gender="F",
        diagnosis="Right Breast Lump",
        chief_complaints="Swelling in right breast x 6 months",
        general_examination="Young aged patient, conscious, oriented. Pulse: 80/min, Blood pressure: 110/80 mm of Hg, pallor present, no pedal edema.",
        local_examination="Right breast swelling present at 7 o'clock position.",
        operation_notes="She underwent right breast lumpectomy under general anaesthesia.",
        course_in_hospital="Patient was admitted with diagnosis of right breast lump and underwent right breast lumpectomy under general anaesthesia. Post operative she did well & is being discharged in satisfactory condition.",
        treatment_on_discharge="Biopsy report follow-up.",
        advice="Biopsy report follow-up.",
    ),
    dict(
        procedure_name="Breast Lumpectomy - Left", gender="F",
        diagnosis="Left Breast Lump",
        chief_complaints="Swelling in left breast x 6 months",
        general_examination="Young patient, conscious, oriented. Pulse: 80/min, Blood pressure: 110/80 mm of Hg, pallor present, no pedal edema.",
        local_examination="Left breast swelling present.",
        operation_notes="She underwent left breast lumpectomy under general anaesthesia.",
        course_in_hospital="Patient was admitted with diagnosis of left breast lump and underwent left breast lumpectomy under general anaesthesia. Post operative she did well & is being discharged in satisfactory condition.",
        treatment_on_discharge="Biopsy report follow-up.",
        advice="Biopsy report follow-up.",
    ),
    dict(
        procedure_name="Fissure in Ano", gender="F",
        diagnosis="Fissure in Ano",
        chief_complaints="Peri-anal pain & discharge x 1-2 years",
        general_examination="Middle aged patient, conscious, oriented. Pulse: 80/min, Blood pressure: 120/80 mm of Hg, no pallor, no pedal edema.",
        local_examination="Abdomen soft, non tender. Per rectal examination: fissure at 6 o'clock position.",
        operation_notes="She underwent lateral anal sphincterotomy under spinal anaesthesia.",
        course_in_hospital="Patient was admitted with diagnosis of fissure in ano and underwent lateral anal sphincterotomy under spinal anaesthesia. Post operative she did well & is being discharged in satisfactory condition.",
        treatment_on_discharge="High fibre diet.",
        advice="High fibre diet.",
    ),
]


def seed_templates(apps, schema_editor):
    DischargeTemplate = apps.get_model("hms", "DischargeTemplate")
    for t in TEMPLATES:
        t = dict(t)
        t["follow_up"] = STANDARD_FOLLOW_UP
        t["instructions"] = EMERGENCY_INSTRUCTIONS
        DischargeTemplate.objects.update_or_create(
            procedure_name=t.pop("procedure_name"),
            gender=t.pop("gender"),
            defaults=t,
        )


def remove_templates(apps, schema_editor):
    DischargeTemplate = apps.get_model("hms", "DischargeTemplate")
    for t in TEMPLATES:
        DischargeTemplate.objects.filter(
            procedure_name=t["procedure_name"], gender=t["gender"]
        ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("hms", "0066_ipdadmission_discharge_instructions_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_templates, remove_templates),
    ]
