import json

from openai import OpenAI

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required

from ..decorators import role_required
from ..models import Appointment, Consultation, ICDCode


@login_required
def ai_icd_suggest(request):
    """Free-text diagnosis description -> AI-suggested ICD-10 code(s).

    The AI is only used to interpret plain/colloquial language into likely
    WHO ICD-10 codes; the actual codes/descriptions returned to the frontend
    always come from our own ICDCode table (matched by code, dots ignored),
    never from the AI's own text, so a suggestion can always be looked up
    and added exactly like a manual search-box selection.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    if not settings.AI_FEATURES_ENABLED:
        return JsonResponse({"error": "AI features are not configured on this system."})

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid request"}, status=400)

    text = (data.get("text") or "").strip()
    if not text:
        return JsonResponse({"error": "Please describe the diagnosis first."}, status=400)

    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=400,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "icd_suggestions",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "suggestions": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "code": {"type": "string"},
                                        "description": {"type": "string"},
                                    },
                                    "required": ["code", "description"],
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "required": ["suggestions"],
                        "additionalProperties": False,
                    },
                },
            },
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a medical coding assistant for an Indian hospital. "
                        "Always return ONLY valid JSON. No explanation."
                    ),
                },
                {
                    "role": "user",
                    "content": f"""
A doctor typed this plain-language diagnosis description, which may use
colloquial or informal terms rather than exact medical terminology:

"{text}"

List the most likely WHO ICD-10 code(s) for this, most likely first
(at most 5). For each, give the standard ICD-10 code and its official
short clinical description.

Return JSON format:
{{
  "suggestions": [
    {{ "code": "", "description": "" }}
  ]
}}
""",
                },
            ],
        )
        result = json.loads(response.choices[0].message.content or "{}")
    except Exception as e:
        return JsonResponse({"error": f"AI request failed: {e}"}, status=502)

    # Only ever return codes that actually exist in our own ICDCode table —
    # match with dots stripped, since WHO-standard formatting ("K80.20")
    # doesn't always match how a code happens to be stored here ("K8020").
    import re
    from django.db.models import Value, CharField
    from django.db.models.functions import Replace

    def normalize(code):
        return re.sub(r"[^A-Za-z0-9]", "", code or "").upper()

    matched = []
    seen_ids = set()
    for s in (result.get("suggestions") or [])[:5]:
        norm = normalize(s.get("code"))
        if not norm:
            continue
        icd = ICDCode.objects.annotate(
            code_norm=Replace("code", Value("."), Value(""), output_field=CharField())
        ).filter(code_norm__iexact=norm).first()
        if icd and icd.id not in seen_ids:
            seen_ids.add(icd.id)
            matched.append({"id": icd.id, "code": icd.code, "description": icd.description})

    if not matched:
        return JsonResponse({
            "suggestions": [],
            "error": "AI couldn't find a matching code in our ICD-10 database for that description. Try rephrasing, or use the search box above.",
        })

    return JsonResponse({"suggestions": matched})


client = OpenAI(api_key=settings.OPENAI_API_KEY)


def ai_full_opd(request):
    if request.method == "POST":
        if not settings.AI_FEATURES_ENABLED:
            return JsonResponse({"error": "AI features are not configured on this system."})

        complaints = request.POST.getlist("complaints[]")
        exam = request.POST.getlist("exam[]")
        vitals = request.POST.get("vitals")
        investigations = request.POST.get("investigation_results")

        prompt = f"""
        You are assisting a General Surgeon in OPD in India.

        Symptoms: {', '.join(complaints)}
        Examination: {', '.join(exam)}
        Vitals: {vitals}
        Investigation Results: {investigations}

        Give structured output:

        Probable Diagnosis:
        Required Investigations:
        Final Diagnosis:
        Treatment Plan:
        Prescription:
        Advice:
        Red Flag:

        Keep short and practical.
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        result_text = response.choices[0].message.content or ""

        return JsonResponse({"result": result_text})


@login_required
@role_required("doctor", "admin")
def ai_clinical_review(request, appointment_id):
    """Second-opinion style AI review built from the FULL saved clinical
    context of a consultation (patient demographics, history, diagnosis,
    investigations, current prescription) — pulled automatically from the
    DB rather than requiring manual entry."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    if not settings.AI_FEATURES_ENABLED:
        return JsonResponse({"error": "AI features are not configured on this system."})

    appointment = get_object_or_404(
        Appointment.objects.select_related("patient"), id=appointment_id
    )
    patient = appointment.patient
    consultation, _ = Consultation.objects.get_or_create(appointment=appointment)

    def field(value):
        return (value or "").strip()

    residency = ", ".join(
        p for p in [patient.city, patient.district, patient.state] if p
    ) or "Not recorded"

    complaints = list(consultation.symptoms.values_list("name", flat=True))
    if field(consultation.chief_complaints):
        complaints.append(field(consultation.chief_complaints))
    if field(consultation.custom_symptoms):
        complaints.append(field(consultation.custom_symptoms))

    exam_findings = list(consultation.signs.values_list("name", flat=True))
    if field(consultation.examination):
        exam_findings.append(field(consultation.examination))
    if field(consultation.custom_signs):
        exam_findings.append(field(consultation.custom_signs))

    past_history = list(consultation.past_history.values_list("name", flat=True))
    surgical_history = list(consultation.surgical_history.values_list("name", flat=True))

    diagnosis_parts = []
    if field(consultation.diagnosis_text):
        diagnosis_parts.append(field(consultation.diagnosis_text))
    diagnosis_parts += [
        f"{icd.code} - {icd.description}" for icd in consultation.icd_codes.all()
    ]

    investigations_advised = list(consultation.investigations.values_list("name", flat=True))
    if field(consultation.custom_investigations):
        investigations_advised.append(field(consultation.custom_investigations))

    qlv = consultation.quick_lab_values or {}
    qlv_labels = {
        "hb": "Hb", "tlc": "TLC", "platelet": "Platelet", "rbs": "RBS",
        "creatinine": "Creatinine", "urea": "Urea", "sgot": "SGOT", "sgpt": "SGPT",
        "tsh": "TSH", "typhoid": "Typhoid", "mp_test": "MP", "esr": "ESR",
    }
    result_parts = []
    for key, label in qlv_labels.items():
        val = field(qlv.get(key))
        if val:
            result_parts.append(f"{label}: {val}")
    other_label = field(qlv.get("other_label"))
    other_value = field(qlv.get("other_value"))
    if other_label and other_value:
        result_parts.append(f"{other_label}: {other_value}")
    if field(consultation.usg_findings):
        result_parts.append(f"USG: {field(consultation.usg_findings)}")

    rx_lines = [
        f"{p.medicine} {p.dose} {p.frequency} x {p.duration}"
        + (f" ({p.instructions})" if p.instructions else "")
        for p in consultation.prescriptions.all()
    ]

    context_block = (
        f"Patient: {patient.age if patient.age is not None else 'age not recorded'} "
        f"year old {patient.gender}, resident of {residency}.\n\n"
        f"Chief Complaints / Symptoms: {', '.join(complaints) or 'None recorded'}\n"
        f"Examination Findings: {', '.join(exam_findings) or 'None recorded'}\n"
        f"Past History: {', '.join(past_history) or 'None recorded'}\n"
        f"Surgical History: {', '.join(surgical_history) or 'None recorded'}\n"
        f"Diagnosis (incl. ICD-10): {', '.join(diagnosis_parts) or 'Not yet entered'}\n"
        f"Investigations Advised: {', '.join(investigations_advised) or 'None advised'}\n"
        f"Investigation Results: {', '.join(result_parts) or 'No results entered yet'}\n"
        f"Current Prescription: {'; '.join(rx_lines) or 'No medicines prescribed yet'}"
    )

    system_prompt = (
        "You are a clinical decision-support assistant giving a second opinion to the "
        "treating doctor in an Indian OPD/IPD setting. You are NOT diagnosing the "
        "patient or replacing the doctor's judgment. Compare the case against standard "
        "clinical guidelines for this presentation and note anything that seems missing "
        "or worth considering — e.g. a commonly-indicated investigation that hasn't been "
        "ordered, a red-flag symptom not addressed, or a drug interaction/dosing concern "
        "in the current prescription. Suggest additions to the treatment plan only if "
        "genuinely relevant given the data provided. Every point MUST be phrased as an "
        "advisory suggestion for the doctor to consider (e.g. 'Consider also checking...', "
        "'Note: possible interaction between X and Y') — never as a definitive correction, "
        "diagnosis, or instruction. If nothing seems missing, say so briefly instead of "
        "inventing concerns. Return ONLY valid JSON matching the given schema."
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=900,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "clinical_second_opinion",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "considerations": {"type": "array", "items": {"type": "string"}},
                        "treatment_suggestions": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["summary", "considerations", "treatment_suggestions"],
                    "additionalProperties": False,
                },
            },
        },
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context_block},
        ],
    )
    result_text = response.choices[0].message.content or "{}"
    try:
        review = json.loads(result_text)
    except ValueError:
        return JsonResponse({"error": "AI response could not be parsed."}, status=502)

    return JsonResponse({"success": True, "review": review, "context_used": context_block})


@login_required
@role_required("doctor", "admin")
def ai_clinical_scribe(request, appointment_id):
    """AI Clinical Scribe: turns the doctor's rough shorthand notes, typed
    during/after the consultation, into a structured clinical note (HPI /
    Examination / Diagnosis / Plan). Documentation aid only — the doctor
    reviews and edits the result before it is ever saved, same as every
    other AI-assisted field on this model."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    if not settings.AI_FEATURES_ENABLED:
        return JsonResponse({"error": "AI features are not configured on this system."})

    appointment = get_object_or_404(
        Appointment.objects.select_related("patient"), id=appointment_id
    )
    patient = appointment.patient
    consultation, _ = Consultation.objects.get_or_create(appointment=appointment)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid request"}, status=400)

    raw_notes = (data.get("raw_notes") or "").strip()
    if not raw_notes:
        return JsonResponse({"error": "Please type some quick notes first."}, status=400)

    diagnosis_parts = []
    if (consultation.diagnosis_text or "").strip():
        diagnosis_parts.append(consultation.diagnosis_text.strip())
    diagnosis_parts += [
        f"{icd.code} - {icd.description}" for icd in consultation.icd_codes.all()
    ]

    patient_line = (
        f"{patient.age if patient.age is not None else 'age not recorded'} "
        f"year old {patient.gender}"
    )
    known_diagnosis_line = ", ".join(diagnosis_parts) or "Not yet entered"

    system_prompt = (
        "You are an AI clinical scribe for a doctor in an Indian OPD setting. "
        "Convert the doctor's rough, shorthand consultation notes into a clean, "
        "structured clinical note. Use only information stated or clearly implied "
        "in the notes or the known patient context — never invent findings, "
        "vitals, or history that aren't there. If a section has nothing to go on, "
        "write 'Not documented' for that section instead of guessing. Write each "
        "section as plain prose suitable for a medical record, not a bare "
        "restatement of the shorthand. Return ONLY valid JSON matching the given schema."
    )
    user_prompt = (
        f"Patient: {patient_line}.\n"
        f"Diagnosis already recorded for this visit (if any): {known_diagnosis_line}.\n\n"
        f"Doctor's rough notes:\n\"{raw_notes}\""
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=800,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "clinical_scribe_note",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "history_of_present_illness": {"type": "string"},
                            "examination_findings": {"type": "string"},
                            "diagnosis_impression": {"type": "string"},
                            "plan": {"type": "string"},
                        },
                        "required": [
                            "history_of_present_illness", "examination_findings",
                            "diagnosis_impression", "plan",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        sections = json.loads(response.choices[0].message.content or "{}")
    except Exception as e:
        return JsonResponse({"error": f"AI request failed: {e}"}, status=502)

    structured_note = (
        "HISTORY OF PRESENT ILLNESS\n"
        f"{sections.get('history_of_present_illness', '').strip()}\n\n"
        "EXAMINATION FINDINGS\n"
        f"{sections.get('examination_findings', '').strip()}\n\n"
        "DIAGNOSIS / IMPRESSION\n"
        f"{sections.get('diagnosis_impression', '').strip()}\n\n"
        "PLAN\n"
        f"{sections.get('plan', '').strip()}"
    )

    return JsonResponse({"success": True, "structured_note": structured_note})


@login_required
def generate_diet(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    if not settings.AI_FEATURES_ENABLED:
        return JsonResponse({'error': 'AI features are not configured on this system.'})
    import json
    data = json.loads(request.body)
    diagnosis = data.get('diagnosis', '').strip()
    if not diagnosis:
        return JsonResponse({'error': 'No diagnosis'}, status=400)
    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            max_tokens=150,
            messages=[{
                'role': 'user',
                'content': f'Patient diagnosis: {diagnosis}.\nWrite Indian diet chart in exactly 6 lines:\nEarly Morning: ...\nBreakfast: ...\nLunch: ...\nEvening: ...\nDinner: ...\nAvoid: ...\nOnly diet chart, no extra text, 25 words max.'
            }]
        )
        diet = (response.choices[0].message.content or "").strip()
        return JsonResponse({'diet': diet})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


DISCHARGE_POLISH_FIELDS = [
    "diagnosis", "chief_complaint", "general_examination", "local_examination",
    "procedure_done", "ipd_treatment", "course_in_hospital",
    "condition_at_discharge", "discharge_advice",
]


@login_required
def ai_polish_discharge(request):
    """Rewrite the Discharge tab's free-text fields into standard clinical
    discharge-summary documentation style: proper medical terminology,
    standard vitals notation when present, and a coherent narrative
    structure for Course in Hospital — never inventing or altering clinical
    facts, values, units, or medicine names. Purely a text rewrite: takes
    whatever the doctor already typed and returns polished versions of the
    same fields for review before saving; nothing is read from or written
    to the database here."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    if not settings.AI_FEATURES_ENABLED:
        return JsonResponse({'error': 'AI features are not configured on this system.'})
    import json
    data = json.loads(request.body)
    fields = {key: (data.get(key) or "").strip() for key in DISCHARGE_POLISH_FIELDS}
    if not any(fields.values()):
        return JsonResponse({'error': 'Nothing to polish — the discharge fields are all empty.'}, status=400)

    field_labels = {
        "diagnosis": "Diagnosis",
        "chief_complaint": "Chief Complaints",
        "general_examination": "General Examination",
        "local_examination": "Local Examination",
        "procedure_done": "Procedure Performed",
        "ipd_treatment": "IPD Treatment",
        "course_in_hospital": "Course in Hospital",
        "condition_at_discharge": "Condition at Discharge",
        "discharge_advice": "Discharge Advice",
    }

    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            max_tokens=1400,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "discharge_polish",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            key: (
                                {
                                    "type": "string",
                                    "description": (
                                        "Empty string if Procedure Performed is empty and this field's "
                                        "own input is empty. Never mention a procedure or anaesthesia "
                                        "unless Procedure Performed is non-empty — see the Course in "
                                        "Hospital instructions for the exact two cases."
                                    ),
                                }
                                if key == "course_in_hospital"
                                else {"type": "string"}
                            )
                            for key in DISCHARGE_POLISH_FIELDS
                        },
                        "required": DISCHARGE_POLISH_FIELDS,
                        "additionalProperties": False,
                    },
                },
            },
            messages=[
                {
                    'role': 'system',
                    'content': (
                        "You are a senior Indian hospital medical scribe finalizing an "
                        "IPD discharge summary into standard clinical documentation "
                        "style — not just a grammar pass. For each field: replace "
                        "colloquial or shorthand phrasing with correct medical "
                        "terminology, and use a consistent, formal clinical tone — "
                        "complete sentences, properly capitalized, correct punctuation. Do "
                        "not silently expand or reinterpret an abbreviation you are not "
                        "certain of — if unsure what one stands for, leave it exactly "
                        "as written rather than guessing.\n\n"
                        "Vitals notation: if a field's text contains vital-sign "
                        "readings (temperature, pulse, blood pressure, SpO2, "
                        "respiratory rate), reformat them into the standard clinical "
                        "line format, e.g. 'Temp: 98.6°F, Pulse: 88/min, BP: 120/80 "
                        "mmHg, SpO2: 98% on room air, RR: 18/min' — but include ONLY "
                        "the vital signs that are actually present in the source text, "
                        "with the exact values/units given (do not convert °F↔°C, and "
                        "do not add a unit that wasn't there). Never invent, guess, or "
                        "default a reading that is not present in the source text.\n\n"
                        "Course in Hospital specifically — there are exactly two "
                        "cases, check Procedure Performed FIRST to know which one "
                        "applies:\n\n"
                        "CASE 1 — Procedure Performed is EMPTY (this is the common "
                        "case for a non-surgical/medical admission). You are FORBIDDEN "
                        "from using the words \"underwent\" or \"anaesthesia\" anywhere "
                        "in Course in Hospital, and forbidden from naming or implying "
                        "any procedure, in this case — there is none, so mentioning one "
                        "would be a fabrication. Instead: rewrite Course in Hospital's "
                        "own input text (if any) as ONE coherent narrative paragraph "
                        "describing how the patient's condition evolved, using ONLY "
                        "information already present in that field's own text (e.g. "
                        "progress notes). If that input is also empty, output an empty "
                        "string for Course in Hospital — do not write anything.\n\n"
                        "CASE 2 — Procedure Performed is NON-EMPTY. Output EXACTLY this "
                        "fixed template, filling the brackets, and nothing else (no "
                        "progress-note content, no details from Condition at Discharge "
                        "or any other field):\n"
                        "\"Patient was admitted with diagnosis of [diagnosis] and "
                        "underwent [procedure name] under [anaesthesia type] anaesthesia "
                        "on [date]. Post operative [he/she] did well & is being "
                        "discharged in satisfactory condition.\"\n"
                        "Fill the brackets ONLY from these exact sources — never invent "
                        "any of them, and never leave a literal \"[...]\" placeholder in "
                        "the output:\n"
                        "- [procedure name], [anaesthesia type], [date]: parse them "
                        "directly out of the Procedure Performed field's own text, which "
                        "is normally phrased 'He/She underwent NAME under TYPE "
                        "anaesthesia on DATE.' — extract NAME/TYPE/DATE from it exactly "
                        "as written. If Procedure Performed does not clearly state a "
                        "date, drop \"on [date]\" entirely rather than inventing one.\n"
                        "- [he/she]: use whichever pronoun Procedure Performed's own "
                        "text already uses (it was already derived from the patient's "
                        "gender) — lowercase it for this mid-sentence use.\n"
                        "- [diagnosis]: take it from the Diagnosis field, stripping any "
                        "leading ICD-10 code (e.g. \"K29.70 - \") and lowercasing the "
                        "first letter unless it's an acronym. If Diagnosis is empty, "
                        "replace ONLY the opening sentence with \"Patient was admitted "
                        "and underwent [procedure name] under [anaesthesia type] "
                        "anaesthesia on [date].\" — the second sentence (\"Post operative "
                        "[he/she] did well & is being discharged in satisfactory "
                        "condition.\") is UNCHANGED and MUST still be included in full "
                        "either way; never stop after the first sentence.\n"
                        "In CASE 2, Course in Hospital may end up non-empty even if its "
                        "own input was empty, purely because Procedure Performed has "
                        "content — that is expected, not an invented fact; this is the "
                        "ONLY field allowed to behave that way.\n\n"
                        "Absolute rule, overriding all of the above: do NOT invent, "
                        "add, remove, or alter any clinical fact — no diagnoses, "
                        "symptoms, findings, vital values, lab values, medicine names, "
                        "doses, frequencies, durations, dates, or instructions may "
                        "change in meaning. Only reword/reformat what is already "
                        "there. If a field's input is empty, return it as an empty "
                        "string — never fabricate content for a blank field — except "
                        "Course in Hospital's procedure template as described above, "
                        "which is assembled directly from the Procedure Performed and "
                        "Diagnosis fields, not fabricated. Return ONLY valid JSON, one "
                        "key per field, no explanation."
                    ),
                },
                {
                    'role': 'user',
                    'content': "Rewrite each of these discharge-summary fields:\n\n" + "\n\n".join(
                        f"{field_labels[key]}: {fields[key] or '(empty)'}"
                        for key in DISCHARGE_POLISH_FIELDS
                    ),
                },
            ],
        )
        raw = response.choices[0].message.content or "{}"
        parsed = json.loads(raw)
        result = {}
        for key in DISCHARGE_POLISH_FIELDS:
            # An input left blank must stay blank — belt-and-suspenders on top
            # of the prompt instruction, in case the model still fills one in.
            # Course in Hospital is the one deliberate exception: it's allowed
            # to come back non-blank even from a blank input, but only when
            # Procedure Performed has content (the procedure-confirmation
            # link) — never fabricated out of nothing.
            if key == "course_in_hospital":
                allowed = bool(fields["course_in_hospital"]) or bool(fields["procedure_done"])
            else:
                allowed = bool(fields[key])
            result[key] = (parsed.get(key, "") or "").strip() if allowed else ""

        # Deterministic safety net for Course in Hospital: gpt-4o-mini
        # occasionally ignores the "don't mention a procedure when Procedure
        # Performed is empty" instruction and either fabricates an
        # anaesthesia/procedure mention out of nothing, or leaks a literal
        # "[bracket placeholder]" from the template text in the prompt. Since
        # we know deterministically when a procedure mention would be a
        # fabrication (Procedure Performed is empty), catch it here rather
        # than trust the model — fall back to the doctor's own original
        # Course in Hospital text (untouched) if either happens.
        if not fields["procedure_done"]:
            ch_lower = result["course_in_hospital"].lower()
            if "anaesthesia" in ch_lower or "underwent" in ch_lower or "[" in result["course_in_hospital"]:
                result["course_in_hospital"] = fields["course_in_hospital"]
        else:
            # Case 2 (a procedure exists): the model occasionally drops the
            # required closing sentence, truncating right after the date.
            # Since the template is fixed and fully derivable from
            # procedure_done + diagnosis, rebuild it ourselves whenever the
            # model's own output doesn't comply, rather than trust a retry.
            ch = result["course_in_hospital"]
            if "satisfactory condition" not in ch.lower() or "[" in ch:
                import re
                m = re.match(
                    r"(he|she)\s+underwent\s+(.+?)\s+under\s+(.+?)\s+anaesthesia\s+on\s+(.+?)\.?\s*$",
                    (result["procedure_done"] or "").strip(),
                    re.IGNORECASE,
                )
                if m:
                    pronoun, name, anaesthesia, date = (g.strip() for g in m.groups())
                    dx = re.sub(
                        r"^\s*[A-Za-z]\d[\w.]*\s*[:\-]\s*", "", (result["diagnosis"] or "").strip()
                    ).strip().rstrip(".")
                    if dx and not dx[:2].isupper():
                        dx = dx[0].lower() + dx[1:]
                    lead = f"Patient was admitted with diagnosis of {dx} and underwent" if dx else "Patient was admitted and underwent"
                    result["course_in_hospital"] = (
                        f"{lead} {name} under {anaesthesia} anaesthesia on {date}. "
                        f"Post operative {pronoun.lower()} did well & is being discharged in satisfactory condition."
                    )

        return JsonResponse({'fields': result})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def transcribe_dictation(request):
    """Voice dictation for the OPD free-text fields.

    Accepts a short browser-recorded audio clip (multipart field ``audio``),
    sends it to the OpenAI Whisper API and returns the transcript. The front
    end appends this text to whichever field was focused when recording began.

    No ``language=`` is passed on purpose: Whisper auto-detects, which is what
    keeps mixed Hindi/English ("Hinglish") dictation working instead of being
    forced to English-only.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    if not settings.AI_FEATURES_ENABLED:
        return JsonResponse({'error': 'AI features are not configured on this system.'})

    audio = request.FILES.get('audio')
    if not audio:
        return JsonResponse({'error': 'No audio received'}, status=400)
    # Whisper's hard limit is 25 MB. Our clips are a few seconds of speech, so
    # anything near that is almost certainly a mistake; reject early.
    if audio.size > 25 * 1024 * 1024:
        return JsonResponse({'error': 'Audio clip too large (max 25 MB).'}, status=400)
    if audio.size < 1024:
        return JsonResponse({'error': 'Nothing was recorded — try again.'}, status=400)

    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        result = client.audio.transcriptions.create(
            model='whisper-1',
            file=(audio.name or 'dictation.webm', audio.read(), audio.content_type or 'audio/webm'),
            response_format='text',
        )
        text = (result if isinstance(result, str) else getattr(result, 'text', '') or '').strip()
        return JsonResponse({'text': text})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def generate_lama_consent(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    if not settings.AI_FEATURES_ENABLED:
        return JsonResponse({'error': 'AI features are not configured on this system.'})
    import json
    data = json.loads(request.body)
    diagnosis = data.get('diagnosis', '').strip()
    plan = data.get('plan', '').strip()
    if not diagnosis or not plan:
        return JsonResponse({'error': 'Diagnosis and Plan/Advice are both required'}, status=400)
    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            max_tokens=900,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "lama_consent",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "consent_en": {"type": "string"},
                            "consent_hi": {"type": "string"},
                        },
                        "required": ["consent_en", "consent_hi"],
                        "additionalProperties": False,
                    },
                },
            },
            messages=[
                {
                    'role': 'system',
                    'content': (
                        "You are a senior Indian surgeon drafting a formal LAMA "
                        "(Leave Against Medical Advice) consent note for a hospital "
                        "record. Always return ONLY valid JSON. No explanation."
                    ),
                },
                {
                    'role': 'user',
                    'content': f"""
Diagnosis: {diagnosis}
Recommended treatment / plan advised: {plan}

Write "consent_en": a formal 6-7 line consent/refusal paragraph in English,
first person plural ("We, the patient/attendant..."), covering:
- the diagnosis
- the treatment/admission that was recommended
- name 2-3 SPECIFIC, clinically accurate complications that could plausibly
  result from NOT receiving this exact treatment for this exact diagnosis
  (reason about the actual anatomy/pathology involved -- a fracture, a
  stone, an infection, etc. each have different realistic complications).
  Do not fall back to a generic, one-size-fits-all list of complications --
  they must be medically appropriate to THIS diagnosis specifically.
- a statement that the patient/attendant was informed of these risks in
  a language they understand, and voluntarily chose to decline/leave
  against medical advice, releasing the hospital and treating doctor
  from responsibility for adverse outcomes resulting from this decision.

Then write "consent_hi": a faithful Hindi translation of that exact
paragraph (Devanagari script), same meaning and structure.

Plain paragraph text only in each field, no headings, no markdown, no
bullet points.
""",
                },
            ],
        )
        raw = response.choices[0].message.content or "{}"
        parsed = json.loads(raw)
        return JsonResponse({
            'consent_en': parsed.get('consent_en', '').strip(),
            'consent_hi': parsed.get('consent_hi', '').strip(),
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def generate_referral_letter(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    if not settings.AI_FEATURES_ENABLED:
        return JsonResponse({'error': 'AI features are not configured on this system.'})
    import json
    data = json.loads(request.body)

    appointment_id = data.get('appointment_id')
    appointment = get_object_or_404(
        Appointment.objects.select_related("patient", "doctor"),
        id=appointment_id,
    )
    patient = appointment.patient

    referred_to = data.get('referred_to', '').strip()
    reason = data.get('reason', '').strip()
    urgency = data.get('urgency', '').strip()
    diagnosis = data.get('diagnosis', '').strip()
    clinical_summary = data.get('clinical_summary', '').strip()
    referral_type = data.get('referral_type', 'investigation').strip() or 'investigation'

    if not referred_to or not reason:
        return JsonResponse({'error': 'Referred To and Reason for Referral are both required'}, status=400)

    patient_age = f"{patient.age_years} Yrs" if patient.age_years else "age not on record"

    if referral_type == 'treatment':
        type_instruction = (
            "This is a TREATMENT REFERRAL — the patient is being referred to a "
            "specialist for ongoing evaluation and management of their condition "
            "by that specialist, not just a single test. The letter must:\n"
            "- request the receiving specialist to take over/share in the ongoing "
            "  evaluation and clinical management of the patient's condition\n"
            "- avoid framing this as a request for one specific test/procedure to "
            "  be performed and reported back -- focus on continuity of care"
        )
    else:
        type_instruction = (
            "This is an INVESTIGATION REFERRAL — the patient is being referred "
            "to get a specific test/scan/procedure done. The letter must:\n"
            "- clearly request that the specific test/procedure be performed\n"
            "- request that the findings/report be shared back with the "
            "  referring doctor for further management"
        )

    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            max_tokens=500,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "referral_letter",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "letter_text": {"type": "string"},
                        },
                        "required": ["letter_text"],
                        "additionalProperties": False,
                    },
                },
            },
            messages=[
                {
                    'role': 'system',
                    'content': (
                        "You are a senior Indian physician drafting a formal, concise "
                        "referral letter body to a fellow doctor/hospital for a hospital "
                        "record. Always return ONLY valid JSON. No explanation."
                    ),
                },
                {
                    'role': 'user',
                    'content': f"""
Patient: {patient.full_name}, {patient_age}, {patient.gender}, UHID {patient.uhid}
Diagnosis: {diagnosis or 'not specified'}
Clinical summary (complaints / examination): {clinical_summary or 'not specified'}
Reason for referral: {reason}
Urgency: {urgency or 'routine'}
Referring to: {referred_to}
Referring doctor: {appointment.doctor.full_name}

{type_instruction}

Write "letter_text": the BODY of a formal referral letter, 4-6 sentences,
professional medical tone, third person for the patient. It must:
- identify the patient by name, age and sex, and briefly the presenting
  clinical picture / diagnosis
- state the reason this patient is being referred, incorporating the
  urgency naturally into the wording (e.g. "requires urgent evaluation" /
  "may be seen on a routine basis" / "requires emergency management")
- follow the referral-type instruction above for what exactly is being
  requested of the receiving doctor/facility, and offer to share any
  further records/reports needed

Do NOT include a salutation ("Dear Doctor,"), a closing ("Yours
sincerely,"), or a signature line -- only the paragraph body text, since
those are added separately by the letter template. Plain paragraph text,
no markdown, no bullet points, no headings.
""",
                },
            ],
        )
        raw = response.choices[0].message.content or "{}"
        parsed = json.loads(raw)
        return JsonResponse({
            'letter_text': parsed.get('letter_text', '').strip(),
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def generate_ai_medicines(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    if not settings.AI_FEATURES_ENABLED:
        return JsonResponse({'error': 'AI features are not configured on this system.'})

    try:
        data = json.loads(request.body)

        diagnosis = data.get('diagnosis', '').strip()
        drug_list = data.get('drug_list', [])

        if not diagnosis:
            return JsonResponse({'error': 'No diagnosis provided'}, status=400)

        # Convert drug list to string
        drug_str = ', '.join(drug_list) if drug_list else 'No drugs available'

        client = OpenAI(api_key=settings.OPENAI_API_KEY)

        # 🔥 Strong Prompt + JSON Enforcement
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=600,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "ai_medicines",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "medicines": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "medicine": {"type": "string"},
                                        "dose": {"type": "string"},
                                        "frequency": {"type": "string"},
                                        "duration": {"type": "string"},
                                        "instructions": {"type": "string"},
                                    },
                                    "required": ["medicine", "dose", "frequency", "duration", "instructions"],
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "required": ["medicines"],
                        "additionalProperties": False,
                    },
                },
            },
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior Indian physician. "
                        "Always return ONLY valid JSON. No explanation."
                    ),
                },
                {
                    "role": "user",
                    "content": f"""
Patient diagnosis: {diagnosis}

Available medicines in pharmacy:
{drug_str}

STRICT RULES:
- Prescribe only clinically correct medicines
- Prefer available medicines if appropriate
- If not available, write (not in stock)
- DO NOT add unnecessary medicines
- Maximum 3 to 5 medicines only

SURGICAL NOTE:
For appendicitis, hernia, cholelithiasis → give pre-operative medicines
(antibiotics, analgesics, antispasmodics, PPI)

DOSING RULES:
- Frequency must be fixed (e.g. Once daily (1-0-0), Twice daily (1-0-1))
- Duration must be fixed (e.g. 5 days, 7 days, 14 days)
- DO NOT use "as needed"

Return JSON format:
{{
  "medicines": [
    {{
      "medicine": "",
      "dose": "",
      "frequency": "",
      "duration": "",
      "instructions": ""
    }}
  ]
}}
"""
                }
            ]
        )

        # ✅ Direct JSON parsing (no regex)
        result_text = response.choices[0].message.content
        result = json.loads(result_text)

        # ✅ Validation layer
        validated_medicines = []
        required_keys = ["medicine", "dose", "frequency", "duration", "instructions"]

        for med in result.get("medicines", []):
            if all(key in med for key in required_keys):
                
                # Mark not in stock if not matched
                if drug_list and not any(med["medicine"].lower() in d.lower() for d in drug_list):
                    med["medicine"] += " (not in stock)"

                validated_medicines.append({
                    "medicine": med.get("medicine", ""),
                    "dose": med.get("dose", ""),
                    "frequency": med.get("frequency", ""),
                    "duration": med.get("duration", ""),
                    "instructions": med.get("instructions", "")
                })

        return JsonResponse({"medicines": validated_medicines})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON from AI'}, status=500)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

