# hms/fhir_builder.py
# ABDM FHIR R4 Bundle Builder
import uuid
import datetime


def build_patient_resource(patient):
    """Convert Patient model → FHIR R4 Patient resource"""
    return {
        "resourceType": "Patient",
        "id": str(patient.uhid),
        "identifier": [
            {
                "system": "https://healthid.ndhm.gov.in",
                "value": patient.abha_number or patient.uhid
            }
        ],
        "name": [{"text": patient.full_name}],
        "gender": patient.gender.lower(),
        "birthDate": str(patient.date_of_birth) if patient.date_of_birth else None,
        "telecom": [{"system": "phone", "value": patient.mobile_no}],
        "address": [{"text": patient.address}],
    }


def build_op_consultation_bundle(consultation):
    """Build FHIR R4 Bundle for OP Consultation"""
    patient = consultation.appointment.patient
    doctor  = consultation.appointment.doctor

    # ── Vitals as Observations ──────────────────────────
    observations = []

    if consultation.bp:
        observations.append({
            "resourceType": "Observation",
            "status": "final",
            "code": {"coding": [{
                "system": "http://loinc.org",
                "code": "55284-4",
                "display": "Blood pressure"
            }]},
            "valueString": consultation.bp
        })

    if consultation.pulse:
        observations.append({
            "resourceType": "Observation",
            "status": "final",
            "code": {"coding": [{
                "system": "http://loinc.org",
                "code": "8867-4",
                "display": "Heart rate"
            }]},
            "valueString": consultation.pulse
        })

    if consultation.spo2:
        observations.append({
            "resourceType": "Observation",
            "status": "final",
            "code": {"coding": [{
                "system": "http://loinc.org",
                "code": "59408-5",
                "display": "Oxygen saturation"
            }]},
            "valueString": consultation.spo2
        })

    if consultation.weight:
        observations.append({
            "resourceType": "Observation",
            "status": "final",
            "code": {"coding": [{
                "system": "http://loinc.org",
                "code": "29463-7",
                "display": "Body weight"
            }]},
            "valueString": consultation.weight
        })

    # ── Prescriptions as MedicationRequests ─────────────
    medications = []
    for rx in consultation.prescriptions.all():
        medications.append({
            "resourceType": "MedicationRequest",
            "status": "active",
            "intent": "order",
            "medicationCodeableConcept": {"text": rx.medicine},
            "dosageInstruction": [{
                "text": f"{rx.dose} {rx.frequency} for {rx.duration}"
            }]
        })

    # ── Diagnosis Condition ──────────────────────────────
    conditions = []
    if consultation.diagnosis_text or consultation.diagnosis_icd:
        condition = {
            "resourceType": "Condition",
            "clinicalStatus": {
                "coding": [{"code": "active"}]
            },
            "code": {
                "text": consultation.diagnosis_text or ""
            }
        }
        if consultation.diagnosis_icd:
            condition["code"]["coding"] = [{
                "system": "http://hl7.org/fhir/sid/icd-10",
                "code": consultation.diagnosis_icd.code,
                "display": consultation.diagnosis_icd.description
            }]
            # Add SNOMED if available
            if consultation.diagnosis_icd.snomed_code:
                condition["code"]["coding"].append({
                    "system": "http://snomed.info/sct",
                    "code": consultation.diagnosis_icd.snomed_code,
                    "display": consultation.diagnosis_icd.snomed_description or ""
                })
        conditions.append(condition)

    # ── Build Bundle ─────────────────────────────────────
    bundle = {
        "resourceType": "Bundle",
        "id": str(uuid.uuid4()),
        "type": "document",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "entry": [
            {"resource": build_patient_resource(patient)},
            {"resource": {
                "resourceType": "Practitioner",
                "name": [{"text": doctor.full_name}]
            }},
            *[{"resource": obs} for obs in observations],
            *[{"resource": med} for med in medications],
            *[{"resource": con} for con in conditions],
        ]
    }
    return bundle


def build_discharge_summary_bundle(admission):
    """Build FHIR R4 Bundle for Discharge Summary"""
    patient = admission.patient

    bundle = {
        "resourceType": "Bundle",
        "id": str(uuid.uuid4()),
        "type": "document",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "entry": [
            {"resource": build_patient_resource(patient)},
            {"resource": {
                "resourceType": "Composition",
                "status": "final",
                "type": {"coding": [{
                    "system": "http://loinc.org",
                    "code": "18842-5",
                    "display": "Discharge summary"
                }]},
                "title": "Discharge Summary",
                "date": str(
                    admission.discharge_date.date()
                    if admission.discharge_date
                    else datetime.date.today()
                ),
                "section": [
                    {
                        "title": "Chief Complaint",
                        "text": {"div": admission.chief_complaint or ""}
                    },
                    {
                        "title": "Diagnosis",
                        "text": {"div": admission.diagnosis or ""}
                    },
                    {
                        "title": "Course in Hospital",
                        "text": {"div": admission.course_in_hospital or ""}
                    },
                    {
                        "title": "Discharge Summary",
                        "text": {"div": admission.discharge_summary or ""}
                    },
                    {
                        "title": "Discharge Advice",
                        "text": {"div": admission.discharge_advice or ""}
                    },
                ]
            }}
        ]
    }
    return bundle


def build_lab_report_bundle(bill_item):
    """Build FHIR R4 Bundle for Lab Report"""
    patient = bill_item.bill.patient
    investigation = bill_item.investigation

    observations = []
    for result in bill_item.results.all():
        obs = {
            "resourceType": "Observation",
            "status": "final",
            "code": {
                "text": result.parameter.name
            },
            "valueString": result.value,
        }
        # Add LOINC code if available
        if result.parameter.loinc_code:
            obs["code"]["coding"] = [{
                "system": "http://loinc.org",
                "code": result.parameter.loinc_code,
                "display": result.parameter.loinc_display or result.parameter.name
            }]
        observations.append(obs)

    bundle = {
        "resourceType": "Bundle",
        "id": str(uuid.uuid4()),
        "type": "document",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "entry": [
            {"resource": build_patient_resource(patient)},
            {"resource": {
                "resourceType": "DiagnosticReport",
                "status": "final",
                "code": {"text": investigation.name},
                "result": [
                    {"reference": f"Observation/{i}"}
                    for i in range(len(observations))
                ]
            }},
            *[{"resource": obs} for obs in observations],
        ]
    }
    return bundle