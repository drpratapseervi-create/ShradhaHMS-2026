from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ..decorators import role_required
from ..models import (
    Ward, Bed, Patient, Doctor, IPDAdmission, IPDVital, IPDMedication,
    IPDDischargeMedication, DischargeTemplate, IPDProgressNote,
    IPDSymptomHistory, IPDTreatmentHistory, IPDProcedure,
    InvestigationBill, InvestigationBillItem, Investigation, DrugMaster,
    Consultation,
)
from ..forms import IPDAdmissionForm


@login_required
def ipd_dashboard(request):
    wards = Ward.objects.prefetch_related("bed_set").all()
    admissions = IPDAdmission.objects.filter(
        status="ADMITTED"
    ).select_related("patient", "bed", "doctor")
    return render(request, "ipd/dashboard.html", {
        "wards": wards,
        "admissions": admissions,
    })


@login_required
def admit_bed(request, bed_id):
    bed = get_object_or_404(Bed, id=bed_id)

    if bed.is_occupied:
        return redirect("hms:ipd_dashboard")

    if request.method == "POST":
        patient_id = request.POST.get("patient")
        doctor_id  = request.POST.get("doctor")

        chief_complaint    = request.POST.get("chief_complaint", "")
        symptoms           = request.POST.get("symptoms", "")
        diagnosis          = request.POST.get("diagnosis", "")
        icd_code           = request.POST.get("icd_code", "")
        attendant_name     = request.POST.get("attendant_name", "")
        attendant_relation = request.POST.get("attendant_relation", "")
        attendant_mobile   = request.POST.get("attendant_mobile", "")

        admission_date = timezone.now()
        admission_date_raw = request.POST.get("admission_date", "").strip()
        if admission_date_raw:
            parsed_date = parse_datetime(admission_date_raw)
            if parsed_date:
                if timezone.is_naive(parsed_date):
                    parsed_date = timezone.make_aware(parsed_date, timezone.get_current_timezone())
                admission_date = parsed_date

        if not patient_id:
            patients = Patient.objects.all().order_by("full_name")
            doctors  = Doctor.objects.select_related("department").order_by("full_name")
            return render(request, "ipd/admit_form.html", {
                "bed": bed,
                "patients": patients,
                "doctors": doctors,
                "error": "Please select a patient before admitting."
            })

        patient = get_object_or_404(Patient, id=int(patient_id))

        doctor = None
        department = None
        if doctor_id:
            doctor = Doctor.objects.select_related("department").filter(id=int(doctor_id)).first()
            if doctor and doctor.department:
                department = doctor.department

        auto_diagnosis = diagnosis
        if not auto_diagnosis:
            last_consultation = Consultation.objects.filter(
                appointment__patient=patient
            ).order_by("-created_at").first()
            if last_consultation:
                auto_diagnosis = last_consultation.diagnosis_text

        last_ipd = IPDAdmission.objects.order_by("-id").first()
        if last_ipd and last_ipd.ipd_no:
            last_num = int(last_ipd.ipd_no.split("-")[-1])
            new_ipd = f"IPD-{last_num+1:05d}"
        else:
            new_ipd = "IPD-00001"

        admission = IPDAdmission.objects.create(
            ipd_no             = new_ipd,
            patient            = patient,
            doctor             = doctor,
            department         = department,
            ward               = bed.ward,
            bed                = bed,
            chief_complaint    = chief_complaint,
            symptoms           = symptoms,
            diagnosis          = auto_diagnosis,
            icd_code           = icd_code,
            attendant_name     = attendant_name,
            attendant_relation = attendant_relation,
            attendant_mobile   = attendant_mobile,
            admission_date     = admission_date,
            status             = "ADMITTED",
        )

        bed.is_occupied = True
        bed.save()

        return redirect("hms:ipd_dashboard")

    patients = Patient.objects.all().order_by("full_name")
    doctors  = Doctor.objects.select_related("department").order_by("full_name")
    return render(request, "ipd/admit_form.html", {
        "bed": bed,
        "patients": patients,
        "doctors": doctors,
    })


@login_required
def ipd_discharge(request, admission_id):
    admission = get_object_or_404(IPDAdmission, id=admission_id)
    admission.discharge_date = timezone.now()
    admission.status = "DISCHARGED"
    admission.save()
    bed = admission.bed
    bed.is_occupied = False
    bed.save()
    return redirect("hms:ipd_dashboard")


@login_required
@role_required("doctor", "admin", "nursing")
def admit_patient(request):

    if request.method == "POST":
        form = IPDAdmissionForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("hms:ipd_dashboard")
        selected_patient_id = request.POST.get("patient")
    else:
        form = IPDAdmissionForm()
        selected_patient_id = request.GET.get("patient")

    try:
        selected_patient_id = int(selected_patient_id)
    except (TypeError, ValueError):
        selected_patient_id = None

    patients = Patient.objects.all().order_by("full_name")
    doctors = Doctor.objects.all().order_by("full_name")
    return render(request, "ipd/admit_form.html", {
        "form": form,
        "patients": patients,
        "doctors": doctors,
        "selected_patient_id": selected_patient_id,
    })


def procedure_performed_text(admission):
    """The single, authoritative "Procedure Performed" text for an admission
    — shared by the Discharge tab and the printed PDF so they can never show
    two different answers for the same admission.

    Precedence: a structured Procedure-tab entry, when one exists, ALWAYS
    wins — generating "He/she underwent [name] under [anaesthesia]
    anaesthesia on [date]." per entry (oldest first) — even overriding
    whatever free text is already saved in admission.procedure_done, since
    that text can go stale/wrong once a real Procedure entry is recorded
    (e.g. leftover text from before the Procedure tab existed, or a typo
    unrelated to anything else on the chart). Only when there is no
    structured entry yet does the doctor's own saved procedure_done text
    apply, then finally the Treatment tab history as a last resort — this
    keeps existing admissions from before the Procedure tab untouched.
    """
    procedures = list(admission.procedures.all())
    if procedures:
        pronoun = "She" if (admission.patient.gender or "").strip().lower().startswith("f") else "He"
        return " ".join(
            f"{pronoun} underwent {p.procedure_name} under {p.anaesthesia_type} "
            f"anaesthesia on {p.procedure_date.strftime('%d %b %Y')}."
            for p in reversed(procedures)
        )
    if (admission.procedure_done or "").strip():
        return admission.procedure_done.strip()
    _tr = [
        h.treatment_plan.strip() for h in admission.treatment_history.all().order_by("-recorded_at")
        if h.treatment_plan and h.treatment_plan.strip()
    ]
    if _tr:
        return "\n".join(reversed(_tr))
    return (admission.treatment_plan or "").strip()


_CC_OPTIONS = {
    "fever", "cough", "body ache", "body pain", "throat pain", "sore throat",
    "loss of appetite", "fatigue", "lethargy", "fatigue/lethargy",
    "abdominal pain", "nausea", "vomiting", "nausea/vomiting",
}


def _filter_chief_complaints(text):
    items = [s.strip() for s in (text or "").split(",") if s.strip()]
    if not items:
        return ""
    looks_like_prose = any(len(it) > 45 or ". " in it or it.endswith(".") for it in items)
    keep = [it for it in items if it.lower() in _CC_OPTIONS] if looks_like_prose else items
    return ", ".join(keep)


def chief_complaint_text(admission):
    """The single, authoritative "Chief Complaints" text for an admission —
    shared by the Discharge tab and the printed PDF, mirroring
    procedure_performed_text() above: the Symptoms tab's checked complaints
    (filtered through _filter_chief_complaints) ALWAYS win when any exist,
    even overriding whatever free text is already saved in
    admission.chief_complaint, since that can go stale/wrong (e.g. leftover
    placeholder text unrelated to what's actually checked on the Symptoms
    tab). Falls back to the most recent Symptom-history snapshot, then to
    that saved text, only when the Symptoms tab has nothing usable.
    """
    text = _filter_chief_complaints(admission.symptoms)
    if not text:
        for _h in admission.symptom_history.all().order_by("-recorded_at"):
            text = _filter_chief_complaints(_h.symptoms)
            if text:
                break
    if text:
        return text
    return (admission.chief_complaint or "").strip()


@login_required
def ipd_patient_file(request, admission_id):
    admission = get_object_or_404(IPDAdmission, id=admission_id)

    if request.method == "POST":
        form_type = request.POST.get("form_type")
        
        if form_type == "vitals":
            IPDVital.objects.create(
                admission=admission,
                pulse=request.POST.get("pulse") or None,
                bp=request.POST.get("bp", ""),
                temperature=request.POST.get("temperature") or None,
                spo2=request.POST.get("spo2") or None,
                rr=request.POST.get("rr") or None
            )
            
        elif form_type == "symptoms":
            # 1. Grab all selected inputs from the checklist array
            selected_list = request.POST.getlist("symptoms_list")
            
            # 2. Join checkboxes together into a clean text string 
            symptoms_text = ", ".join(selected_list)
            admission.symptoms = symptoms_text
            admission.save()

            # 3. Log a historical snapshot of this save (only if something was selected)
            if symptoms_text:
                IPDSymptomHistory.objects.create(
                    admission=admission,
                    symptoms=symptoms_text,
                )

        elif form_type == "diagnosis":
            admission.diagnosis = request.POST.get("diagnosis", "").strip()

        elif form_type == "treatment":
            treatment_text = request.POST.get("treatment_plan", "").strip()
            if treatment_text:
                admission.treatment_plan = treatment_text
                IPDTreatmentHistory.objects.create(
                    admission=admission,
                    treatment_plan=treatment_text,
                )

        elif form_type == "procedure":
            procedure_name   = request.POST.get("procedure_name", "").strip()
            anaesthesia_type = request.POST.get("anaesthesia_type", "").strip()
            procedure_date   = request.POST.get("procedure_date") or None
            if procedure_name and anaesthesia_type and procedure_date:
                IPDProcedure.objects.create(
                    admission=admission,
                    procedure_name=procedure_name,
                    anaesthesia_type=anaesthesia_type,
                    procedure_date=procedure_date,
                )

        elif form_type == "medication":
            drug_id = request.POST.get("drug_id", "").strip()
            drug_obj = DrugMaster.objects.filter(id=drug_id, is_active=True).first() if drug_id.isdigit() else None
            medicine_name = drug_obj.name if drug_obj else drug_id

            if medicine_name:
                IPDMedication.objects.create(
                    admission=admission,
                    drug=drug_obj,
                    medicine_name=medicine_name,
                    dose=request.POST.get("dose", ""),
                    route=request.POST.get("route", ""),
                    frequency=request.POST.get("frequency", ""),
                )

        elif form_type == "discharge_medication":
            drug_id = request.POST.get("drug_id", "").strip()
            drug_obj = DrugMaster.objects.filter(id=drug_id, is_active=True).first() if drug_id.isdigit() else None
            medicine_name = drug_obj.name if drug_obj else drug_id

            if medicine_name:
                dose = request.POST.get("dose", "").strip()
                if not dose and drug_obj:
                    dose = drug_obj.default_dose or drug_obj.strength
                frequency = request.POST.get("frequency", "").strip() or (drug_obj.default_frequency if drug_obj else "")
                duration = request.POST.get("duration", "").strip() or (drug_obj.default_duration if drug_obj else "")
                instructions = request.POST.get("instructions", "").strip() or (drug_obj.default_instructions if drug_obj else "")

                IPDDischargeMedication.objects.create(
                    admission=admission,
                    drug=drug_obj,
                    medicine_name=medicine_name,
                    dose=dose,
                    route=request.POST.get("route", ""),
                    frequency=frequency,
                    duration=duration,
                    instructions=instructions,
                )

        elif form_type == "discharge_medication_delete":
            med_id = request.POST.get("discharge_medication_id", "")
            if med_id.isdigit():
                IPDDischargeMedication.objects.filter(id=med_id, admission=admission).delete()

        elif form_type == "discharge_medication_bulk":
            med_ids = [i for i in request.POST.getlist("medication_ids") if i.isdigit()]
            source_meds = IPDMedication.objects.filter(id__in=med_ids, admission=admission)
            for src in source_meds:
                IPDDischargeMedication.objects.create(
                    admission=admission,
                    drug=src.drug,
                    medicine_name=src.medicine_name,
                    dose=src.dose,
                    route=src.route,
                    frequency=src.frequency,
                )

        elif form_type == "investigations":
            inv_ids = [i for i in request.POST.getlist("investigations") if i.isdigit()]
            if inv_ids:
                bill, _ = InvestigationBill.objects.get_or_create(
                    admission=admission,
                    defaults={"patient": admission.patient, "paid": False, "total_amount": 0},
                )
                already_ordered = set(
                    bill.items.values_list("investigation_id", flat=True)
                )
                for inv in Investigation.objects.filter(id__in=inv_ids).exclude(id__in=already_ordered):
                    InvestigationBillItem.objects.create(
                        bill=bill,
                        investigation=inv,
                        price=inv.price,
                        added_by="DOCTOR",
                    )
                bill.total_amount = sum(bill.items.values_list("price", flat=True))
                bill.save()

        elif form_type == "progress":
            subjective = request.POST.get("subjective", "").strip()
            objective  = request.POST.get("objective", "").strip()
            assessment = request.POST.get("assessment", "").strip()
            plan       = request.POST.get("plan", "").strip()
            if subjective or objective or assessment or plan:
                IPDProgressNote.objects.create(
                    admission=admission,
                    doctor=admission.doctor,
                    subjective=subjective,
                    objective=objective,
                    assessment=assessment,
                    plan=plan,
                )

        elif form_type == "discharge":
            admission.diagnosis               = request.POST.get("diagnosis", "").strip()
            admission.chief_complaint         = request.POST.get("chief_complaint", "").strip()
            admission.general_examination     = request.POST.get("general_examination", "").strip()
            admission.local_examination       = request.POST.get("local_examination", "").strip()
            admission.inv_hb                  = request.POST.get("inv_hb", "").strip()
            admission.inv_tlc                 = request.POST.get("inv_tlc", "").strip()
            admission.inv_platelet_count      = request.POST.get("inv_platelet_count", "").strip()
            admission.inv_rbs                 = request.POST.get("inv_rbs", "").strip()
            admission.inv_hiv                 = request.POST.get("inv_hiv", "").strip()
            admission.inv_hbsag               = request.POST.get("inv_hbsag", "").strip()
            admission.inv_usg                 = request.POST.get("inv_usg", "").strip()
            admission.procedure_done          = request.POST.get("procedure_done", "").strip()
            admission.ipd_treatment           = request.POST.get("ipd_treatment", "").strip()
            admission.course_in_hospital      = request.POST.get("course_in_hospital", "").strip()
            admission.condition_at_discharge  = request.POST.get("condition_at_discharge", "").strip()
            admission.discharge_advice        = request.POST.get("discharge_advice", "").strip()
            admission.follow_up_date          = request.POST.get("follow_up_date") or None
            if not admission.discharge_date:
                admission.discharge_date = timezone.now()

        admission.save()
        discharge_med_actions = ("discharge_medication", "discharge_medication_delete", "discharge_medication_bulk")
        tab = "discharge" if form_type in discharge_med_actions else form_type
        anchor = "#discharge-medications-section" if form_type in discharge_med_actions else ""
        return redirect(f"/ipd/patient/{admission.id}/?tab={tab}{anchor}")

    vitals     = IPDVital.objects.filter(admission=admission).order_by("-recorded_at")
    medications = IPDMedication.objects.filter(admission=admission)
    discharge_medications = IPDDischargeMedication.objects.filter(admission=admission).order_by("-created_at")
    drug_masters = DrugMaster.objects.filter(is_active=True).order_by("sort_order", "category", "name")
    discharge_templates = list(
        DischargeTemplate.objects.filter(is_active=True).values(
            "id", "procedure_name", "gender",
            "diagnosis", "chief_complaints", "general_examination", "local_examination",
            "operation_notes", "course_in_hospital",
            "advice",
        )
    )
    symptom_history = IPDSymptomHistory.objects.filter(admission=admission).order_by("-recorded_at")
    treatment_history = IPDTreatmentHistory.objects.filter(admission=admission).order_by("-recorded_at")
    procedure_history = IPDProcedure.objects.filter(admission=admission)  # Meta.ordering: -procedure_date, -recorded_at

    ordered_investigations = (
        InvestigationBillItem.objects
        .filter(bill__admission=admission)
        .select_related("investigation__category", "bill")
        .prefetch_related("results", "results__parameter")
        .order_by("-id")
    )
    ordered_investigation_ids = {item.investigation_id for item in ordered_investigations}
    available_investigations = Investigation.objects.filter(is_active=True).select_related("category")

    # Optional helper: converts text back to a list so boxes stay checked on refresh
    saved_symptoms_list = [s.strip() for s in admission.symptoms.split(",")] if admission.symptoms else []

    # ── Discharge Summary: prefill values pulled from the rest of this IPD file ──
    # Feeds the "Load from patient record" button + the empty-field autofill on the
    # Discharge tab. Purely advisory: the JS only writes these into blank fields and
    # never touches text the doctor has already entered/saved (same rule as the
    # existing "Load Template" dropdown, which stays untouched).

    # Chief Complaints  ←  chief_complaint_text() (see its definition above
    # this view): the Symptoms tab's checked complaints always win when any
    # exist, overriding stale/mismatched text already saved in
    # admission.chief_complaint. Shared with the printed PDF so the two can
    # never disagree — same pattern as procedure_performed_text().
    chief_complaint_prefill = chief_complaint_text(admission)

    # Investigations  ←  matching ordered-investigation results (by investigation /
    # parameter name). Each field: (exact-match names, substring-match names,
    # substring names that DISqualify a row). Left blank when nothing matches.
    _INV_MATCH = {
        "inv_hb":             (("hb",), ("haemoglobin", "hemoglobin"), ("a1c", "glycat")),
        "inv_tlc":            (("tlc",), ("total leukocyte", "total leucocyte", "total wbc", "wbc count"), ()),
        "inv_platelet_count": (("plt", "platelet count"), ("platelet count", "platelets"), ()),
        "inv_rbs":            (("rbs",),
                               ("random blood sugar", "blood sugar random", "sugar random",
                                "sugar (random)", "sugar - random", "random blood glucose",
                                "glucose random", "glucose (random)"),
                               ("fasting", "prandial", "ppbs", "fbs")),
        "inv_hiv":            (("hiv",), ("hiv", "anti hiv", "anti-hiv"), ()),
        "inv_hbsag":          (("hbsag",), ("hbsag", "hbs ag", "hepatitis b surface", "australia antigen"), ()),
        "inv_usg":            (("usg",), ("usg", "ultrasound", "ultrasonograph", "sonograph"), ()),
    }
    inv_prefill = {f: "" for f in _INV_MATCH}
    for _item in ordered_investigations:
        _inv_name = (_item.investigation.name or "").strip().lower()
        for _res in _item.results.all():
            _val = (_res.value or "").strip()
            if not _val:
                continue
            _names = (_inv_name, (_res.parameter.name or "").strip().lower())
            for _field, (_exact, _contains, _exclude) in _INV_MATCH.items():
                if inv_prefill[_field]:
                    continue
                if any(bad in n for bad in _exclude for n in _names):
                    continue
                if any(n in _exact for n in _names) or any(sub in n for sub in _contains for n in _names):
                    inv_prefill[_field] = _val

    # Procedure Performed  ←  procedure_performed_text() (see its definition
    # above this view): a structured Procedure-tab entry always wins when
    # one exists, overriding stale/mismatched text already saved in
    # admission.procedure_done; falls back to that saved text, then to the
    # Treatment tab history, for admissions with no structured entry yet.
    # Shared with the printed PDF so the two can never disagree.
    procedure_prefill = procedure_performed_text(admission)

    # IPD Treatment  ←  a narrative built from the inpatient Medication Chart
    # (the treatment actually given during the stay, kept separate from Discharge
    # Medications). Course in Hospital  ←  the Progress Notes (SOAP), chronological.
    # Each is blank if its source has nothing recorded.
    import re

    def _freq_words(raw):
        """Normalise a frequency string ('(1-0-1) twice daily', 'TDS', 'OD', …)
        into plain words, falling back to the raw string when unrecognised."""
        f = (raw or "").strip()
        if not f:
            return ""
        low = f.lower()
        for phrase, words in (
            ("thrice daily", "thrice daily"), ("three times", "thrice daily"),
            ("twice daily", "twice daily"), ("two times", "twice daily"),
            ("four times", "four times daily"),
            ("once daily", "once daily"), ("once a day", "once daily"),
            ("every 6 hours", "every 6 hours"), ("every 8 hours", "every 8 hours"),
            ("at bedtime", "at bedtime"), ("as needed", "as needed"),
        ):
            if phrase in low:
                return words
        abbr = {
            "od": "once daily", "hs": "at bedtime", "qhs": "at bedtime",
            "bd": "twice daily", "bid": "twice daily",
            "tds": "thrice daily", "tid": "thrice daily",
            "qid": "four times daily", "qds": "four times daily",
            "sos": "as needed", "prn": "as needed", "stat": "immediately",
            "q4h": "every 4 hours", "q6h": "every 6 hours",
            "q8h": "every 8 hours", "q12h": "every 12 hours",
        }
        for tok in re.split(r"[^a-z0-9]+", low):
            if tok in abbr:
                return abbr[tok]
        m = re.search(r"(\d)\s*-\s*(\d)\s*-\s*(\d)", low)
        if m:
            n = sum(1 for g in m.groups() if g != "0")
            return {1: "once daily", 2: "twice daily", 3: "thrice daily",
                    4: "four times daily"}.get(n, f)
        return f

    _med_segs, _routes, _is_abx = [], [], False
    for m in medications:
        dose = re.sub(r"\s*\([^)]*\)\s*$", "", (m.dose or "").strip()).strip()  # drop "(100 ml)" tail
        seg = " ".join(x for x in (m.medicine_name, dose, m.route, _freq_words(m.frequency)) if x and x.strip())
        seg = seg.strip()
        if not seg:
            continue
        _med_segs.append(seg)
        _routes.append((m.route or "").lower())
        d = m.drug
        if d and ((d.category or "").lower().startswith("antibiot")
                  or (d.atc_code or "").upper().startswith("J01")):
            _is_abx = True

    def _join_natural(parts):
        if len(parts) == 1:
            return parts[0]
        if len(parts) == 2:
            return f"{parts[0]} and {parts[1]}"
        return ", ".join(parts[:-1]) + f", and {parts[-1]}"

    # diagnosis text for "for the management of …": strip any leading ICD code,
    # trailing period, and lead lowercase unless it starts with an acronym
    _dx = re.sub(r"^\s*[A-Za-z]\d[\w.]*\s*[:\-]\s*", "", (admission.diagnosis or "").strip()).strip().rstrip(".")
    if _dx and not _dx[:2].isupper():
        _dx = _dx[0].lower() + _dx[1:]

    ipd_treatment_prefill = ""
    if _med_segs:
        _all_iv = all("iv" in r for r in _routes if r) and any("iv" in r for r in _routes)
        if _is_abx and _all_iv:
            _lead = "Patient completed a course of intravenous antibiotics during admission consisting of "
        elif _all_iv:
            _lead = "Patient completed a course of intravenous medication during admission consisting of "
        else:
            _lead = "Patient was treated during admission with "
        _sentence = _lead + _join_natural(_med_segs)
        if _dx:
            _sentence += f" for the management of {_dx}"
        ipd_treatment_prefill = _sentence.rstrip() + "."

    _note_lines = []
    for _n in admission.progress_notes.all().order_by("date_time"):
        _bits = []
        if (_n.subjective or "").strip(): _bits.append("S: " + _n.subjective.strip())
        if (_n.assessment or "").strip(): _bits.append("A: " + _n.assessment.strip())
        if (_n.plan or "").strip():       _bits.append("P: " + _n.plan.strip())
        if _bits:
            _note_lines.append(f"{timezone.localtime(_n.date_time):%d %b %Y} — " + "; ".join(_bits))

    # Course in Hospital: when a structured Procedure-tab entry exists, use
    # the fixed admission -> procedure -> discharge narrative template
    # (diagnosis from the Diagnosis tab, procedure/anaesthesia/date from the
    # most recent Procedure-tab entry, pronoun from patient gender) instead
    # of assembling fragments — this is the canonical "what happened" story
    # for a surgical admission. Diagnosis is omitted gracefully if blank.
    # With no structured Procedure entry, fall back to the previous dynamic
    # assembly: a procedure-confirmation line built from whatever
    # procedure_prefill resolves to (admission.procedure_done or Treatment
    # tab history) plus the Progress Notes narrative — blank if neither
    # exists.
    _procedure_list_for_course = list(procedure_history)
    if _procedure_list_for_course:
        _proc = _procedure_list_for_course[0]  # most recent structured entry
        _pronoun_lower = "she" if (admission.patient.gender or "").strip().lower().startswith("f") else "he"
        _admitted_clause = f"Patient was admitted with diagnosis of {_dx} and underwent" if _dx else "Patient was admitted and underwent"
        course_prefill = (
            f"{_admitted_clause} {_proc.procedure_name} under {_proc.anaesthesia_type} "
            f"anaesthesia on {_proc.procedure_date.strftime('%d %b %Y')}. Post operative "
            f"{_pronoun_lower} did well & is being discharged in satisfactory condition."
        )
    else:
        _procedure_for_course = procedure_prefill
        _course_parts = []
        if _procedure_for_course:
            # A label + verbatim quote reads correctly whether Procedure
            # Performed was typed as a short noun phrase ("Laparoscopic
            # appendectomy") or already as a full sentence ("He underwent …
            # anaesthesia.") — embedding either style mid-sentence instead
            # produces a grammatically broken run-on for the latter case.
            _proc_sentence = f"The following procedure was performed during the hospital stay: {_procedure_for_course}"
            if not _proc_sentence.endswith((".", "!", "?")):
                _proc_sentence += "."
            _course_parts.append(_proc_sentence)
        if _note_lines:
            _course_parts.append("\n".join(_note_lines))
        course_prefill = "\n\n".join(_course_parts)

    # Condition at Discharge  ←  a fixed default template sentence (NOT derived
    # from patient data). Prefilled only into an empty field; the doctor edits or
    # replaces it per patient.
    condition_prefill = (
        "Patient is hemodynamically stable, ambulatory, comfortable, and has no "
        "active complaints. Vitals are stable and within normal limits; the "
        "surgical site is clean, healthy."
    )

    # Discharge Advice  ←  a fixed default template (NOT derived from patient
    # data). Prefilled only into an empty field; the doctor edits or replaces
    # it per patient.
    discharge_advice_prefill = (
        "Continue prescribed medications, maintain a light diet with adequate "
        "fluids, and keep the surgical wound clean and dry. Avoid heavy lifting "
        "for 2–4 weeks; return immediately if fever, worsening pain, vomiting, "
        "or wound redness/discharge occurs."
    )

    # General Examination  ←  the latest vitals reading, recorded on the
    # discharge date or within 12h before it (falls back to "now" while the
    # patient hasn't been discharged yet). Blank if nothing that recent exists.
    from datetime import timedelta
    _ref_time = admission.discharge_date or timezone.now()
    _latest_vital = vitals.first()
    general_exam_prefill = ""
    if _latest_vital and (
        _latest_vital.recorded_at.date() == _ref_time.date()
        or _latest_vital.recorded_at >= _ref_time - timedelta(hours=12)
    ):
        _vbits = []
        if _latest_vital.temperature is not None: _vbits.append(f"Temp {_latest_vital.temperature}")
        if _latest_vital.spo2 is not None:        _vbits.append(f"SpO2 {_latest_vital.spo2}%")
        if _latest_vital.rr is not None:          _vbits.append(f"RR {_latest_vital.rr}/min")
        general_exam_prefill = ", ".join(_vbits)

    discharge_autofill = {
        "diagnosis":              (admission.diagnosis or "").strip(),
        "chief_complaint":        chief_complaint_prefill,
        "general_examination":    general_exam_prefill,
        "ipd_treatment":          ipd_treatment_prefill,
        "course_in_hospital":     course_prefill,
        "procedure_done":         procedure_prefill,
        "condition_at_discharge": condition_prefill,
        "discharge_advice":       discharge_advice_prefill,
    }
    discharge_autofill.update(inv_prefill)

    return render(request, "ipd/patient_file.html", {
        "admission":                admission,
        "vitals":                   vitals,
        "medications":              medications,
        "discharge_medications":    discharge_medications,
        "drug_masters":             drug_masters,
        "discharge_templates":      discharge_templates,
        "saved_symptoms_list":      saved_symptoms_list,
        "symptom_history":          symptom_history,
        "treatment_history":        treatment_history,
        "procedure_history":        procedure_history,
        "available_investigations": available_investigations,
        "ordered_investigations":   ordered_investigations,
        "ordered_investigation_ids": ordered_investigation_ids,
        "discharge_autofill":       discharge_autofill,
        "procedure_done_display":   procedure_prefill,
        "chief_complaint_display":  chief_complaint_prefill,
        "ai_enabled":               settings.AI_FEATURES_ENABLED,
    })


@login_required
def discharge_pdf(request, admission_id):
    admission   = get_object_or_404(IPDAdmission, id=admission_id)
    medications = IPDDischargeMedication.objects.filter(admission=admission).order_by("id")
    return render(request, "ipd/discharge_pdf.html", {
        "admission":              admission,
        "patient":                admission.patient,
        "doctor":                 admission.doctor,
        "ward":                   admission.ward,
        "bed":                    admission.bed,
        "medications":            medications,
        "procedure_done_display":  procedure_performed_text(admission),
        "chief_complaint_display": chief_complaint_text(admission),
    })


@login_required
def progress_notes_pdf(request, admission_id):
    admission = get_object_or_404(IPDAdmission, id=admission_id)
    notes = IPDProgressNote.objects.filter(
        admission=admission
    ).order_by("-created_at")
    return render(request, "ipd/progress_notes_pdf.html", {
        "admission": admission,
        "notes":     notes,
    })

