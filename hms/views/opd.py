import csv
import json

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.db import transaction
from django.db.models import Q
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_date

from ..decorators import role_required
from ..models import (
    Patient, Appointment, Consultation, Prescription,
    Investigation, InvestigationBill, InvestigationBillItem, ICDCode,
    DrugMaster, VillageMaster, Symptom, Sign, PastHistory, SurgicalHistory,
    AdviceOption, DietAdviceOption, FollowUpNotePhrase, MedicalImage,
    IPDAdmission,
)
from ..forms import PatientForm, AppointmentForm, ConsultationForm
from ..utils import render_to_pdf
from ..services.whatsapp import (
    send_opd_visit_thankyou, send_consultation_started, send_prescription_pdf,
    WhatsAppSendError,
)
from ..abdm.services.hip import HIPService
from ._shared import logger


@login_required
@role_required("reception", "admin", "doctor", "nursing")
def patient_create(request):
    if request.method == "POST":
        form = PatientForm(request.POST)
        if form.is_valid():
            patient = form.save(commit=False)
            if not patient.date_of_birth:
                age_val = request.POST.get("age")
                if age_val:
                    patient.age_years = int(age_val)
            patient.save()

            # ← Check which button was clicked
            if "save_and_book" in request.POST:
                return redirect(f"/appointments/new/?patient={patient.pk}")
            return redirect("hms:patient_update", pk=patient.pk)
        else:
            print(form.errors)
    else:
        form = PatientForm()

    return render(request, "patients/patient_form.html", {
        "form": form,
        "villages": VillageMaster.objects.all(),
    })


@login_required
def appointment_create(request):
    form = AppointmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        appt = form.save(commit=False)
        appt.status = "Scheduled"
        appt.appointment_type = "New"
        if appt.payment_mode != "FREE" and appt.fee and appt.fee > 0:
            appt.is_paid = True
        appt.save()

        # ── NEW: Check which button was clicked ──
        if 'go_to_consultation' in request.POST:
            return redirect("hms:start_consultation", appointment_id=appt.id)
        else:
            return redirect("hms:print_opd", appointment_id=appt.id)

    return render(request, "appointment_form.html", {"form": form})


@login_required
def print_opd(request, appointment_id):
    appointment = get_object_or_404(
        Appointment.objects.select_related("patient", "doctor"),
        id=appointment_id,
    )
    return render(request, "opd_receipt_a4.html", {
        "appointment": appointment,
        "printed_on": timezone.now(),
    })


@login_required
@role_required("doctor", "admin")
def start_consultation(request, appointment_id):
    appointment = get_object_or_404(
        Appointment.objects.select_related("patient", "doctor"),
        id=appointment_id,
    )
    consultation, created = Consultation.objects.get_or_create(appointment=appointment)
    if created:
        # First time this appointment's consultation screen has been opened --
        # the closest proxy this system has for "the patient has arrived for
        # their OPD consultation" (there's no separate reception check-in step).
        try:
            send_consultation_started(appointment)
        except (WhatsAppSendError, ValueError):
            logger.exception(
                "Failed to send consultation-started WhatsApp message for appointment %s",
                appointment.id,
            )
    prescriptions = Prescription.objects.filter(consultation=consultation)

    if request.method == "POST":
        print("ADVICE:", request.POST.get("advice"))
        print("DIET:", request.POST.get("diet_advice"))
        print("FOLLOWUP:", request.POST.get("follow_up_date"))
        form = ConsultationForm(request.POST, instance=consultation)
        if form.is_valid():
            with transaction.atomic():
                obj = form.save(commit=False)
                obj.appointment = appointment
                obj.last_modified_by = request.user.username

                complaints_manual = request.POST.get("complaints_manual", "").strip()
                exam_manual = request.POST.get("exam_manual", "").strip()
                if complaints_manual:
                    obj.chief_complaints = complaints_manual
                if exam_manual:
                    obj.examination = exam_manual

                # ── Save advice, diet, follow-up ──
                obj.advice          = request.POST.get("advice", "").strip()
                obj.procedures_performed = request.POST.get("procedures_performed", "").strip()
                obj.diet_advice     = request.POST.get("diet_advice", "").strip()
                obj.follow_up_date  = request.POST.get("follow_up_date") or None
                obj.follow_up_notes = request.POST.get("follow_up_notes", "").strip()
                obj.custom_investigations = request.POST.get("custom_investigations", "")

                # Free-text entries under Chief Complaints / Examination Findings —
                # this consultation only, never saved to the Symptom / Sign masters.
                obj.custom_symptoms = request.POST.get("custom_symptoms", "").strip()
                obj.custom_signs    = request.POST.get("custom_signs", "").strip()

                obj.surgery_date    = request.POST.get("surgery_date") or None
                obj.past_history_date = request.POST.get("past_history_date") or None

                # ── Refusal of Admission / LAMA Consent ──
                obj.lama_declined = bool(request.POST.get("lama_declined"))
                obj.lama_diagnosis = request.POST.get("lama_diagnosis", "").strip()
                obj.lama_plan = request.POST.get("lama_plan", "").strip()
                obj.lama_consent_en = request.POST.get("lama_consent_en", "").strip()
                obj.lama_consent_hi = request.POST.get("lama_consent_hi", "").strip()
                obj.lama_attendant_name = request.POST.get("lama_attendant_name", "").strip()
                obj.lama_attendant_relation = request.POST.get("lama_attendant_relation", "").strip()
                obj.lama_signed_name = request.POST.get("lama_signed_name", "").strip()
                lama_signature_data = request.POST.get("lama_signature_data", "").strip()
                if lama_signature_data:
                    obj.lama_signature_data = lama_signature_data
                if obj.lama_declined and not obj.lama_signed_at:
                    obj.lama_signed_at = timezone.now()

                # ── Referral Note ──
                obj.referral_flag = bool(request.POST.get("referral_flag"))
                obj.referral_to = request.POST.get("referral_to", "").strip()
                obj.referral_reason = request.POST.get("referral_reason", "").strip()
                obj.referral_type = request.POST.get("referral_type", "investigation").strip()
                obj.referral_urgency = request.POST.get("referral_urgency", "").strip()
                obj.referral_letter_text = request.POST.get("referral_letter_text", "").strip()

                # ── Quick Lab Values (manual outside/patient-reported entry) ──
                obj.quick_lab_values = {
                    "hb":           request.POST.get("qlv_hb", "").strip(),
                    "tlc":          request.POST.get("qlv_tlc", "").strip(),
                    "platelet":     request.POST.get("qlv_platelet", "").strip(),
                    "rbs":          request.POST.get("qlv_rbs", "").strip(),
                    "creatinine":   request.POST.get("qlv_creatinine", "").strip(),
                    "urea":         request.POST.get("qlv_urea", "").strip(),
                    "sgot":         request.POST.get("qlv_sgot", "").strip(),
                    "sgpt":         request.POST.get("qlv_sgpt", "").strip(),
                    "tsh":          request.POST.get("qlv_tsh", "").strip(),
                    "typhoid":      request.POST.get("qlv_typhoid", "").strip(),
                    "mp_test":      request.POST.get("qlv_mp_test", "").strip(),
                    "esr":          request.POST.get("qlv_esr", "").strip(),
                    "other_label":  request.POST.get("qlv_other_label", "").strip(),
                    "other_value":  request.POST.get("qlv_other_value", "").strip(),
                }

                obj.save()

                obj.symptoms.set(request.POST.getlist("symptoms"))
                obj.signs.set(request.POST.getlist("signs"))
                obj.past_history.set(request.POST.getlist("past_history"))
                obj.surgical_history.set(request.POST.getlist("surgical_history"))

                # ── Save multiple ICD codes ──
                icd_ids = request.POST.getlist("icd_codes[]")
                print("ICD IDS RECEIVED:", icd_ids)
                if icd_ids:
                    obj.icd_codes.set(icd_ids)
                else:
                    obj.icd_codes.clear()

                inv_ids = request.POST.getlist("investigations")
                obj.investigations.set(inv_ids)
                obj.lab_advised = bool(inv_ids)

                # ── Re-apply before second save ──
                obj.advice          = request.POST.get("advice", "").strip()
                obj.diet_advice     = request.POST.get("diet_advice", "").strip()
                obj.follow_up_date  = request.POST.get("follow_up_date") or None
                obj.custom_investigations = request.POST.get("custom_investigations", "")
                obj.follow_up_notes = request.POST.get("follow_up_notes", "").strip()
                obj.save()

                if inv_ids:
                    bill, created = InvestigationBill.objects.get_or_create(
                        consultation=obj,
                        defaults={
                            "patient": appointment.patient,
                            "paid": False,
                            "total_amount": 0,
                        },
                    )
                    if created:
                        total = 0
                        for inv in obj.investigations.all():
                            InvestigationBillItem.objects.create(
                                bill=bill,
                                investigation=inv,
                                price=inv.price,
                                added_by="DOCTOR",
                            )
                            total += inv.price
                        bill.total_amount = total
                        bill.save()

                Prescription.objects.filter(consultation=obj).delete()
                medicines = request.POST.getlist("medicine[]")
                doses     = request.POST.getlist("dose[]")
                freqs     = request.POST.getlist("frequency[]")
                durs      = request.POST.getlist("duration[]")
                instrs    = request.POST.getlist("instructions[]")
                atc_codes = request.POST.getlist("atc_code[]")
                for i, m in enumerate(medicines):
                    if m.strip():
                        Prescription.objects.create(
                            consultation=obj,
                            medicine=m,
                            dose=doses[i] if i < len(doses) else "",
                            frequency=freqs[i] if i < len(freqs) else "",
                            duration=durs[i] if i < len(durs) else "",
                            instructions=instrs[i] if i < len(instrs) else "",
                            atc_code=atc_codes[i] if i < len(atc_codes) else "",
                        )

                # ── Mark visit complete (sent only by the "Finish" button, not
                # the per-tab "Next" autosave) → trigger the OPD thank-you
                # WhatsApp message, once, on the transition into "Completed" ──
                if request.POST.get("mark_complete") == "1" and appointment.status != "Completed":
                    appointment.status = "Completed"
                    appointment.save(update_fields=["status"])
                    try:
                        send_opd_visit_thankyou(appointment)
                    except (WhatsAppSendError, ValueError):
                        logger.exception(
                            "Failed to send OPD visit thank-you WhatsApp message for appointment %s",
                            appointment.id,
                        )
                    HIPService.notify_opd_consultation(obj)

                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    # AJAX auto-save (e.g. the "Next" button) shows its own JS toast —
                    # a Django message here would never be rendered/consumed and would
                    # just accumulate in the session until the next full page load.
                    return JsonResponse({"success": True})
                messages.success(request, "Consultation saved successfully.")
                return redirect("hms:start_consultation", appointment_id=appointment.id)
        elif request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"success": False, "error": "Please check the form for errors."}, status=400)
    else:
        form = ConsultationForm(instance=consultation)

    previous_consultations = Consultation.objects.filter(
        appointment__patient=appointment.patient
    ).exclude(id=consultation.id).select_related(
        "appointment", "appointment__doctor", "diagnosis_icd"
    ).prefetch_related(
        "symptoms", "signs", "icd_codes", "prescriptions"
    ).order_by("-appointment__date", "-appointment__time")

    previous_visits = [
        {
            "id": c.id,
            "date_str": c.appointment.date.strftime("%b %d, %Y"),
            "doctor": c.appointment.doctor.full_name,
            "pulse": c.pulse,
            "bp": c.bp,
            "spo2": c.spo2,
            "weight": c.weight,
            "quick_lab_values": c.quick_lab_values or {},
            "chief_complaints": c.chief_complaints,
            "symptoms": [s.name for s in c.symptoms.all()],
            "examination": c.examination,
            "signs": [s.name for s in c.signs.all()],
            "diagnosis_text": c.diagnosis_text,
            "icd_codes": [f"{i.code} — {i.description}" for i in c.icd_codes.all()],
            "advice": c.advice,
            "diet_advice": c.diet_advice,
            "follow_up_date": c.follow_up_date.strftime("%b %d, %Y") if c.follow_up_date else "",
            "prescriptions": [
                {
                    "medicine": p.medicine,
                    "dose": p.dose,
                    "frequency": p.frequency,
                    "duration": p.duration,
                    "instructions": p.instructions,
                }
                for p in c.prescriptions.all()
            ],
        }
        for c in previous_consultations
    ]

    followup_phrases = list(
        FollowUpNotePhrase.objects.filter(is_active=True)
        .order_by("sort_order", "text")
        .values_list("text", flat=True)
    )

    return render(request, "opd/consultation.html", {
        "appointment":  appointment,
        "consultation": consultation,
        "form":         form,
        "previous_visits": previous_visits,
        "previous_visits_json": json.dumps(previous_visits).replace("<", "\\u003c"),
        "investigations": Investigation.objects.filter(is_active=True).order_by("sort_order", "name"),
        "prescriptions":  prescriptions,
        "symptoms": Symptom.objects.filter(
            department=appointment.department, is_active=True
        ).order_by("sort_order", "name"),
        "signs": Sign.objects.filter(
            department=appointment.department, is_active=True
        ).order_by("sort_order", "name"),
        "past_histories": PastHistory.objects.filter(is_active=True),
        "surgical_histories": SurgicalHistory.objects.filter(is_active=True),
        "advice_options": AdviceOption.objects.filter(is_active=True),
        "diet_options": DietAdviceOption.objects.filter(is_active=True),
        "followup_phrases": followup_phrases,
        "followup_phrases_json": json.dumps(followup_phrases).replace("<", "\\u003c"),
        "medical_images": MedicalImage.objects.filter(
            consultation=consultation
        ).order_by("-created_at"),
        "drug_masters": DrugMaster.objects.filter(is_active=True).order_by("sort_order", "category", "name"),
        "icd_quick_codes": ICDCode.objects.filter(sort_order__lt=9999),
        "icd_categories": ICDCode.CATEGORY_CHOICES,
        "ai_enabled": settings.AI_FEATURES_ENABLED,
    })


@login_required
@role_required("doctor", "admin")
def save_referral_note(request, appointment_id):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    appointment = get_object_or_404(Appointment, id=appointment_id)
    consultation, _ = Consultation.objects.get_or_create(appointment=appointment)
    data = json.loads(request.body)
    consultation.referral_flag = bool(data.get("referral_flag"))
    consultation.referral_to = (data.get("referral_to") or "").strip()
    consultation.referral_urgency = (data.get("referral_urgency") or "").strip()
    consultation.referral_reason = (data.get("referral_reason") or "").strip()
    consultation.referral_type = (data.get("referral_type") or "investigation").strip()
    consultation.referral_letter_text = (data.get("referral_letter_text") or "").strip()
    consultation.save(update_fields=[
        "referral_flag", "referral_to", "referral_urgency",
        "referral_reason", "referral_type", "referral_letter_text",
    ])
    return JsonResponse({"success": True})


def _consultation_pdf_context(appointment):
    """Shared context for opd/consultation_pdf.html -- used by both the
    browser-print view and the WhatsApp-send view so they render identically."""
    consultation = get_object_or_404(Consultation, appointment=appointment)

    def _lines(txt):
        return [ln.strip() for ln in (txt or "").splitlines() if ln.strip()]

    prescriptions = list(Prescription.objects.filter(consultation=consultation))
    # Prescription.atc_code is a snapshot taken at prescribing time (so a later
    # edit to DrugMaster doesn't rewrite history); prescriptions saved before
    # that snapshot existed have it blank, so fall back to a live DrugMaster
    # lookup by name for display only, without overwriting the stored snapshot.
    missing = [p for p in prescriptions if not p.atc_code]
    if missing:
        drug_atc_by_name = {
            name.lower(): atc for name, atc in
            DrugMaster.objects.filter(atc_code__gt="").values_list("name", "atc_code")
        }
        for p in missing:
            p.atc_code = drug_atc_by_name.get(p.medicine.strip().lower(), "")

    return {
        "appointment":           appointment,
        "consultation":          consultation,
        "chief_complaints_list": consultation.symptoms.all(),
        "examination_list":      consultation.signs.all(),
        "past_history_list":     consultation.past_history.all(),
        "surgical_history_list": consultation.surgical_history.all(),
        "custom_symptoms":       _lines(consultation.custom_symptoms),
        "custom_signs":          _lines(consultation.custom_signs),
        "investigations":        consultation.investigations.all(),
        "prescriptions":         prescriptions,
    }


@login_required
def consultation_pdf(request, appointment_id):
    appointment = get_object_or_404(
        Appointment.objects.select_related("patient", "doctor"),
        id=appointment_id,
    )
    return render(request, "opd/consultation_pdf.html", _consultation_pdf_context(appointment))


@login_required
@require_POST
def consultation_send_whatsapp(request, appointment_id):
    appointment = get_object_or_404(
        Appointment.objects.select_related("patient", "doctor"),
        id=appointment_id,
    )
    context = _consultation_pdf_context(appointment)
    pdf_bytes = render_to_pdf("opd/consultation_pdf.html", context).content

    try:
        send_prescription_pdf(appointment, pdf_bytes)
    except ValueError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)
    except WhatsAppSendError:
        logger.exception("Failed to send prescription PDF via WhatsApp for appointment %s", appointment.id)
        return JsonResponse({"success": False, "error": "Failed to send via WhatsApp. Please try again."}, status=502)

    return JsonResponse({"success": True})


def lama_consent_print(request, appointment_id):
    appointment = get_object_or_404(
        Appointment.objects.select_related("patient", "doctor"),
        id=appointment_id,
    )
    consultation = get_object_or_404(Consultation, appointment=appointment)
    return render(request, "opd/lama_consent_print.html", {
        "appointment":   appointment,
        "consultation":  consultation,
    })


@login_required
def referral_letter_print(request, appointment_id):
    appointment = get_object_or_404(
        Appointment.objects.select_related("patient", "doctor"),
        id=appointment_id,
    )
    consultation = get_object_or_404(Consultation, appointment=appointment)
    return render(request, "opd/referral_letter_print.html", {
        "appointment":  appointment,
        "consultation": consultation,
        "printed_on":   timezone.now(),
    })


@login_required
def medical_certificate_print(request, appointment_id):
    """NMC Sickness/Leave & Fitness certificate (Code of Medical Ethics
    Regulations 2002, Appendix II) — fixed wording, only the blanks below
    are filled in. Replaces the old free-text/AI-drafted certificate."""
    appointment = get_object_or_404(
        Appointment.objects.select_related("patient", "doctor"),
        id=appointment_id,
    )
    consultation = Consultation.objects.filter(appointment=appointment).first()
    patient = appointment.patient

    # Diagnosis prefill: a previously-saved certificate wins; else this
    # visit's consultation; else the patient's most recent past diagnosis
    # (mirrors the IPD discharge-summary prefill rule — advisory only, the
    # doctor edits the field before printing).
    diagnosis_prefill = consultation.sickness_diagnosis if consultation else ""
    if not diagnosis_prefill and consultation:
        parts = []
        if consultation.diagnosis_text:
            parts.append(consultation.diagnosis_text)
        parts += [f"{icd.code} – {icd.description}" for icd in consultation.icd_codes.all()]
        diagnosis_prefill = "; ".join(parts)
    if not diagnosis_prefill:
        past = (
            Consultation.objects
            .filter(appointment__patient=patient)
            .exclude(diagnosis_text="")
            .order_by("-appointment__date", "-id")
            .first()
        )
        if past:
            diagnosis_prefill = past.diagnosis_text

    doctor_name = appointment.doctor.full_name if appointment.doctor else "Pratap Senecha"
    doctor_reg_no = (
        (appointment.doctor.registration_no if appointment.doctor else "")
        or "RMC No-27994"
    )

    # Most recent IPD stay for this patient, if any — source for the
    # admission/discharge-based date suggestions below. Advisory only.
    last_admission = (
        IPDAdmission.objects.filter(patient=patient).order_by("-admission_date").first()
    )

    # Absence range: a previously-saved value wins; else a suggested range
    # from the IPD stay (admission → discharge/today), else from the
    # consultation's follow-up date, else left blank for manual entry.
    absence_from = consultation.absence_from_date if consultation else None
    absence_to = consultation.absence_to_date if consultation else None
    days_absent = consultation.days_absent if consultation else None
    if not absence_from and last_admission:
        absence_from = last_admission.admission_date.date()
        absence_to = (
            last_admission.discharge_date.date() if last_admission.discharge_date
            else timezone.now().date()
        )
    elif not absence_from and consultation and consultation.follow_up_date:
        absence_from = appointment.date
        absence_to = consultation.follow_up_date
    if absence_from and absence_to and not days_absent:
        days_absent = (absence_to - absence_from).days + 1

    # Fitness effective date: only auto-filled when a discharge date exists.
    fitness_effective = consultation.fitness_effective_date if consultation else None
    if not fitness_effective and last_admission and last_admission.discharge_date:
        fitness_effective = last_admission.discharge_date.date()

    place_of_examination = (
        (consultation.place_of_examination if consultation else "")
        or "Shradha Hospital & Multispeciality Centre, Pani Ki Do Tanki, Surajpole, Pali (Raj.)"
    )
    date_of_issue = (consultation.date_of_issue if consultation else None) or timezone.now().date()

    # Certificate No: auto-generated from the appointment id, not stored —
    # deterministic per appointment so reprints always show the same number.
    certificate_no = f"SHMC/MC/{date_of_issue.year}/{appointment.id:05d}"

    # Which part(s) to default to: nothing saved yet → Part A; a Part A
    # already issued for this consultation → default to showing both (the
    # doctor is now also certifying recovery); anything else saved → keep it.
    if consultation and consultation.certificate_part:
        certificate_part_initial = "both" if consultation.certificate_part == "A" else consultation.certificate_part
    else:
        certificate_part_initial = "A"

    return render(request, "opd/medical_certificate_print.html", {
        "appointment":                  appointment,
        "consultation":                 consultation,
        "patient":                      patient,
        "diagnosis_prefill":            diagnosis_prefill,
        "doctor_name":                  doctor_name,
        "doctor_reg_no":                doctor_reg_no,
        "certificate_part_initial":     certificate_part_initial,
        "absence_from_initial":         absence_from,
        "absence_to_initial":           absence_to,
        "days_absent_initial":          days_absent,
        "fitness_effective_initial":    fitness_effective,
        "place_of_examination_initial": place_of_examination,
        "date_of_issue_initial":        date_of_issue,
        "certificate_no":               certificate_no,
        "printed_on":                   timezone.now(),
    })


@login_required
def save_medical_certificate(request, appointment_id):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    appointment = get_object_or_404(Appointment, id=appointment_id)
    consultation, _ = Consultation.objects.get_or_create(appointment=appointment)
    data = json.loads(request.body)

    def to_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def to_date(value):
        # parse_date() calls date.fromisoformat() internally, which raises
        # TypeError (not ValueError) on None — so an empty/missing blank
        # must short-circuit here rather than reach parse_date at all.
        value = (value or "").strip()
        return parse_date(value) if value else None

    consultation.certificate_part = (data.get("certificate_part") or "").strip()
    consultation.sickness_diagnosis = (data.get("sickness_diagnosis") or "").strip()
    consultation.days_absent = to_int(data.get("days_absent"))
    consultation.absence_from_date = to_date(data.get("absence_from_date"))
    consultation.absence_to_date = to_date(data.get("absence_to_date"))
    consultation.fitness_effective_date = to_date(data.get("fitness_effective_date"))
    consultation.place_of_examination = (data.get("place_of_examination") or "").strip()
    consultation.date_of_issue = to_date(data.get("date_of_issue"))

    consultation.save(update_fields=[
        "certificate_part", "sickness_diagnosis", "days_absent",
        "absence_from_date", "absence_to_date", "fitness_effective_date",
        "place_of_examination", "date_of_issue",
    ])
    return JsonResponse({"success": True})


@login_required
@role_required("doctor", "admin")
def save_clinical_scribe(request, appointment_id):
    """Persists the AI Clinical Scribe's raw notes + reviewed structured
    note only — never the rest of the consultation, so this can be saved
    independently without touching anything else on the record."""
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    appointment = get_object_or_404(Appointment, id=appointment_id)
    consultation, _ = Consultation.objects.get_or_create(appointment=appointment)
    data = json.loads(request.body)

    consultation.scribe_raw_notes = (data.get("raw_notes") or "").strip()
    consultation.scribe_structured_note = (data.get("structured_note") or "").strip()
    consultation.save(update_fields=["scribe_raw_notes", "scribe_structured_note"])
    return JsonResponse({"success": True})


@login_required
def export_opd_csv(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="opd_register.csv"'
    writer = csv.writer(response)
    writer.writerow(["ID", "Date", "Patient", "Doctor"])
    for a in Appointment.objects.select_related("patient", "doctor"):
        writer.writerow([
            a.id, a.date,
            a.patient.full_name,
            a.doctor.full_name if a.doctor else "",
        ])
    return response


@login_required
def medicine_search(request):
    q = request.GET.get("q", "")
    by_id = request.GET.get("by_id") == "1"
    medicines = DrugMaster.objects.filter(
        Q(name__icontains=q) | Q(generic_name__icontains=q),
        is_active=True
    )[:20]
    results = []
    for m in medicines:
        results.append({
            "id":           m.id if by_id else m.name,
            "text":         m.name,
            "name":         m.name,
            "generic_name": m.generic_name,
            "strength":     m.strength,
        })
    return JsonResponse(results, safe=False)


@login_required
def icd_search(request):
    q = request.GET.get("q", "").strip()
    icds = ICDCode.objects.filter(
        Q(code__icontains=q) | Q(description__icontains=q)
    )[:20]
    return JsonResponse({
        "results": [{"id": i.id, "text": f"{i.code} - {i.description}"} for i in icds]
    })


def opd_register(request):
    today = timezone.now().date()
    appointments = Appointment.objects.filter(
        date=today
    ).select_related("patient", "doctor").order_by("time")
    return render(request, "opd_register.html", {"appointments": appointments})


@login_required
def patient_update(request, pk):
    patient = get_object_or_404(Patient, pk=pk)

    if request.method == "POST":
        form = PatientForm(request.POST, instance=patient)
        if form.is_valid():
            form.save()
            return redirect("hms:patient_update", pk=patient.pk)
    else:
        form = PatientForm(instance=patient)

    return render(request, "patients/patient_form.html", {
        "form": form,
        "villages": VillageMaster.objects.all(),
    })


@login_required
def patient_search_api(request):
    q = request.GET.get("q", "")
    if not q:
        return JsonResponse([], safe=False)
    
    from django.db.models import Q
    patients = Patient.objects.filter(
        Q(uhid__icontains=q) | Q(full_name__icontains=q)  # ← full_name not name
    )[:10]
    
    data = [{"id": p.id, "uhid": p.uhid, "name": p.full_name} for p in patients]
    return JsonResponse(data, safe=False)


@login_required
def patient_gender_api(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    return JsonResponse({"gender": patient.gender})


@login_required
def patient_get_api(request):
    patient_id = request.GET.get('id')
    try:
        p = Patient.objects.get(pk=patient_id)
        return JsonResponse({
            'id': p.pk,
            'full_name': p.full_name,
            'uhid': p.uhid,
        })
    except Patient.DoesNotExist:
        return JsonResponse({}, status=404)


@login_required
def patient_recent_consultation_api(request, patient_id):
    consultation = (
        Consultation.objects
        .filter(appointment__patient_id=patient_id)
        .select_related("diagnosis_icd")
        .prefetch_related("symptoms", "signs")
        .order_by("-created_at")
        .first()
    )
    if not consultation:
        return JsonResponse({"found": False})

    # Chief Complaints / Examination Findings are free-text fields that exist on
    # the model but the OPD consultation UI actually records this via the
    # symptoms/signs checklists (+ custom_symptoms/custom_signs) instead, so
    # pull from whichever of these is actually populated for this consultation.
    symptoms_lines = []
    if consultation.chief_complaints and consultation.chief_complaints.strip():
        symptoms_lines.append(consultation.chief_complaints.strip())

    symptom_names = list(consultation.symptoms.values_list("name", flat=True))
    if consultation.custom_symptoms and consultation.custom_symptoms.strip():
        symptom_names.append(consultation.custom_symptoms.strip())
    if symptom_names:
        symptoms_lines.append("Symptoms: " + ", ".join(symptom_names))

    sign_names = list(consultation.signs.values_list("name", flat=True))
    if consultation.custom_signs and consultation.custom_signs.strip():
        sign_names.append(consultation.custom_signs.strip())
    if sign_names:
        symptoms_lines.append("Signs: " + ", ".join(sign_names))

    if consultation.examination and consultation.examination.strip():
        symptoms_lines.append("Examination: " + consultation.examination.strip())

    diagnosis_text = (consultation.diagnosis_text or "").strip()
    if not diagnosis_text and consultation.diagnosis_icd:
        diagnosis_text = f"{consultation.diagnosis_icd.code} - {consultation.diagnosis_icd.description}"

    return JsonResponse({
        "found": True,
        "consultation_date": consultation.created_at.strftime("%d-%m-%Y"),
        "symptoms": "\n".join(symptoms_lines),
        "diagnosis": diagnosis_text,
    })


@login_required
@role_required("reception", "admin", "doctor", "nursing")
def add_village(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    data = json.loads(request.body)
    name = data.get('name', '').strip()

    if not name:
        return JsonResponse({'error': 'Name required'}, status=400)

    village, created = VillageMaster.objects.get_or_create(name=name)

    return JsonResponse({'id': village.id, 'name': village.name, 'created': created})


@login_required
def add_drug_quick(request):
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        drug = DrugMaster.objects.create(
            name=data.get('name',''),
            generic_name=data.get('generic_name',''),
            strength=data.get('strength',''),
            category=data.get('category',''),
            default_dose=data.get('default_dose',''),
            default_frequency=data.get('default_frequency',''),
            default_duration=data.get('default_duration',''),
            default_instructions=data.get('default_instructions',''),
            is_active=True,
            sort_order=99,
        )
        return JsonResponse({'success': True, 'id': drug.id, 'name': drug.name})
    return JsonResponse({'success': False, 'error': 'Invalid request'})


@login_required
def drug_defaults(request):
    name = request.GET.get('name', '').strip()
    if not name:
        return JsonResponse({'found': False})
    try:
        # Exact match first
        drug = DrugMaster.objects.filter(
            name__iexact=name, is_active=True
        ).first()
        if not drug:
            # Try first word match
            first_word = name.split()[0]
            drug = DrugMaster.objects.filter(
                name__istartswith=first_word, is_active=True
            ).first()
        if drug:
            return JsonResponse({
                'found': True,
                'dose': drug.default_dose or '',
                'frequency': drug.default_frequency or '',
                'duration': drug.default_duration or '',
                'instructions': drug.default_instructions or '',
                'generic_name': drug.generic_name or '',
                'atc_code': drug.atc_code or '',
            })
    except Exception:
        pass
    return JsonResponse({'found': False})

