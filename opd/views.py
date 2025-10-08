# C:\ShradhaHMS_Full\ShradhaHMS_Full\opd\views.py
from django.shortcuts import render
from django.http import HttpResponse
from django.template.loader import get_template
from django.utils import timezone
from xhtml2pdf import pisa
from io import BytesIO

def _render_to_pdf(template_path, context):
    html = get_template(template_path).render(context)
    result = BytesIO()
    pdf = pisa.CreatePDF(src=html, dest=result)
    if pdf.err:
        return False, b""
    return True, result.getvalue()

def opd_prescription(request, appointment_id):
    """
    Browser-printable OPD Prescription page
    (matches Shradha format: vitals grid + clinical notes + 5-column Rx).
    Later, map these stub values from your real Appointment/Patient models.
    """
    ctx = {
        "patient": {"name": "Ram Kumar", "age": "45", "sex": "M", "address": "Pali"},
        "uhid": f"UHID-{appointment_id}",
        "visit_date": timezone.localdate(),
        "visit_time": timezone.localtime(),
        "vitals": {"weight": "70", "bp": "120/80", "pulse": "80", "temp": "98.4", "rr": "18"},
        "complaints": "Abdominal pain since 2 days",
        "observations": "Mild epigastric tenderness",
        "diagnoses": "Acute gastritis",
        "diagnosis_icd": "K29.0",
        "rx_items": [
            {"name": "Cap Pantocid D 20 mg", "frequency": "1 - 0 - 0", "duration": "5 days", "instructions": "After food", "quantity": "5"},
            {"name": "Tab Topcef 200 mg",    "frequency": "1 - 0 - 1", "duration": "5 days", "instructions": "Before food", "quantity": "10"},
        ],
        "precaution": "Avoid spicy food",
        "diet": "Soft diet",
        "follow_up": "After 5 days",
        "now": timezone.localtime(),
    }
    return render(request, "opd/prescription_shradha.html", ctx)

def opd_prescription_pdf(request, appointment_id):
    """PDF version of the OPD Prescription."""
    ctx = {
        "patient": {"name": "Ram Kumar", "age": "45", "sex": "M", "address": "Pali"},
        "uhid": f"UHID-{appointment_id}",
        "visit_date": timezone.localdate(),
        "visit_time": timezone.localtime(),
        "vitals": {"weight": "70", "bp": "120/80", "pulse": "80", "temp": "98.4", "rr": "18"},
        "complaints": "Abdominal pain since 2 days",
        "observations": "Mild epigastric tenderness",
        "diagnoses": "Acute gastritis",
        "diagnosis_icd": "K29.0",
        "rx_items": [
            {"name": "Cap Pantocid D 20 mg", "frequency": "1 - 0 - 0", "duration": "5 days", "instructions": "After food", "quantity": "5"},
            {"name": "Tab Topcef 200 mg",    "frequency": "1 - 0 - 1", "duration": "5 days", "instructions": "Before food", "quantity": "10"},
        ],
        "precaution": "Avoid spicy food",
        "diet": "Soft diet",
        "follow_up": "After 5 days",
        "now": timezone.localtime(),
    }
    ok, pdf = _render_to_pdf("opd/prescription_shradha.html", ctx)
    if not ok:
        return HttpResponse("PDF generation error", status=500)
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = 'inline; filename="opd_prescription.pdf"'
    return resp
