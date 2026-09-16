import os
import json

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.db.models import Q
from django.contrib import messages
from django.contrib.auth.decorators import login_required

from ..decorators import role_required
from ..models import Patient, Doctor, Consultation, MedicalImage, USGReport
from ..forms import USGReportForm
from ..utils import render_to_pdf


@login_required
def upload_medical_image(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    if request.method == "POST":
        image = request.FILES.get("image")
        if image:
            MedicalImage.objects.create(
                patient=patient,
                image_type=request.POST.get("image_type"),
                title=request.POST.get("title"),
                image=image,
                report_text=request.POST.get("report_text"),
                uploaded_by=request.user,
            )
            messages.success(request, "Medical image uploaded successfully.")
        return redirect("hms:dashboard")
    return render(request, "medical/upload_image.html", {"patient": patient})


@login_required
def upload_medical_image_consultation(request, patient_id, consultation_id):
    patient      = get_object_or_404(Patient, id=patient_id)
    consultation = get_object_or_404(Consultation, id=consultation_id)

    if request.method == "POST":
        image_type  = request.POST.get("image_type", "XRAY")
        title       = request.POST.get("title", "").strip()
        image       = request.FILES.get("image")
        report_text = request.POST.get("report_text", "").strip()

        if image and title:
            MedicalImage.objects.create(
                patient      = patient,
                consultation = consultation,
                image_type   = image_type,
                title        = title,
                image        = image,
                report_text  = report_text,
                uploaded_by  = request.user,
            )
            messages.success(request, f"Image '{title}' uploaded successfully.")
        else:
            messages.error(request, "Title and image file are required.")

    return redirect(
        "hms:start_consultation",
        appointment_id=consultation.appointment.id,
    )


@login_required
def delete_medical_image(request, image_id):
    img = get_object_or_404(MedicalImage, id=image_id)

    appointment_id = request.POST.get("appointment_id")
    redirect_to    = request.POST.get("redirect_to", "radiology")

    if img.image:
        if os.path.isfile(img.image.path):
            os.remove(img.image.path)

    img.delete()
    messages.success(request, "Image deleted successfully.")

    if redirect_to == "consultation" and appointment_id:
        return redirect("hms:start_consultation", appointment_id=appointment_id)

    return redirect("hms:radiology_upload")


@login_required
@role_required("doctor", "admin", "nursing", "laboratory")
def radiology_upload(request):
    from hms.dicom import upload_dicom

    search_query = request.GET.get("q", "").strip()
    if search_query:
        patients = Patient.objects.filter(
            Q(full_name__icontains=search_query) |
            Q(uhid__icontains=search_query) |
            Q(mobile_no__icontains=search_query)
        ).order_by("-id")[:50]
    else:
        patients = Patient.objects.all().order_by("-id")[:50]

    if request.method == "POST":
        patient_id  = request.POST.get("patient_id")
        image_type  = request.POST.get("image_type")
        title       = request.POST.get("title", "").strip()
        image       = request.FILES.get("image")
        report_text = request.POST.get("report_text", "").strip()

        errors = []
        if not patient_id: errors.append("Please select a patient.")
        if not title:       errors.append("Please enter a title.")
        if not image:       errors.append("Please select an image file.")

        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            patient = get_object_or_404(Patient, id=patient_id)

            # ✅ DICOM file (.dcm) — upload to Orthanc
            if image.name.lower().endswith('.dcm'):
                dicom_bytes = image.read()
                instance_id = upload_dicom(dicom_bytes)
                if instance_id:
                    MedicalImage.objects.create(
                        patient           = patient,
                        image_type        = image_type,
                        title             = title,
                        report_text       = report_text,
                        uploaded_by       = request.user,
                        dicom_instance_id = instance_id,
                        is_dicom          = True,
                    )
                    messages.success(request,
                        f"✅ DICOM uploaded to Orthanc for "
                        f"{patient.full_name} ({patient.uhid}) "
                        f"— ID: {instance_id[:8]}..."
                    )
                else:
                    messages.error(request,
                        "DICOM upload to Orthanc failed. "
                        "Make sure Orthanc is running on port 8042."
                    )

            # Regular image (JPG/PNG/GIF/WEBP)
            else:
                allowed_types = ["image/jpeg", "image/png",
                                 "image/gif",  "image/webp"]
                if image.content_type not in allowed_types:
                    messages.error(request,
                        "Only image files (JPG, PNG, GIF, WEBP) "
                        "or DICOM (.dcm) files are allowed."
                    )
                else:
                    MedicalImage.objects.create(
                        patient     = patient,
                        image_type  = image_type,
                        title       = title,
                        image       = image,
                        report_text = report_text,
                        uploaded_by = request.user,
                        is_dicom    = False,
                    )
                    messages.success(request,
                        f"✅ Image uploaded for "
                        f"{patient.full_name} ({patient.uhid})"
                    )

            return redirect("hms:radiology_upload")

    return render(request, "lab/radiology_upload.html", {
        "patients":       patients,
        "search_query":   search_query,
        "recent_uploads": MedicalImage.objects.select_related("patient")
                          .order_by("-created_at")[:15],
    })


@login_required
def usg_report_list(request):
    """List USG reports — with patient search filter."""
    q = request.GET.get("q", "").strip()
    reports = USGReport.objects.select_related("patient", "reporting_doctor")

    if q:
        reports = reports.filter(
            Q(patient__full_name__icontains=q) |
            Q(patient__uhid__icontains=q)      |
            Q(report_no__icontains=q)
        )

    return render(request, "hms/usg/usg_report_list.html", {
        "reports": reports[:100],
        "q":       q,
    })


USG_ADVICE_QUICK_OPTIONS = [
    "LFT", "S. Amylase", "X-ray KUB", "IVP", "CT Urography",
    "CECT Abdomen & Pelvis", "MRCP", "TVS", "UPT", "Urine R/E",
]


def _usg_impression_groups():
    from ..models import USGImpressionOption
    options = USGImpressionOption.objects.filter(is_active=True).order_by("category", "sort_order", "text")
    groups = []
    current_key = None
    for opt in options:
        label = opt.get_category_display()
        if label != current_key:
            groups.append((label, []))
            current_key = label
        groups[-1][1].append(opt.text)
    return groups


@login_required
def usg_report_create(request, patient_id=None, bill_item_id=None):
    """Create a new USG report — optionally pre-linked to patient / bill item."""
    patient   = None
    bill_item = None

    if patient_id:
        patient = get_object_or_404(Patient, pk=patient_id)
    if bill_item_id:
        from ..models import InvestigationBillItem
        bill_item = get_object_or_404(InvestigationBillItem, pk=bill_item_id)
        if not patient:
            patient = bill_item.bill.patient

    initial = {}
    if patient:
        initial["patient"] = patient
    if bill_item:
        initial["bill_item"] = bill_item
    initial["findings_text"] = USGReport.default_findings_text(
        "ABDOMEN_PELVIS", gender=patient.gender if patient else None
    )
    initial["clinical_indication"] = "Pain abdomen"
    default_doctor = Doctor.objects.filter(full_name__icontains="Pratap Senecha").first()
    if default_doctor:
        initial.setdefault("referred_by", default_doctor)
        initial.setdefault("reporting_doctor", default_doctor)

    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    form = USGReportForm(request.POST or None, initial=initial)

    if request.method == "POST" and form.is_valid():
        report = form.save(commit=False)
        report.created_by = request.user
        report.save()
        if is_ajax:
            return JsonResponse({"success": True, "report_id": report.pk})
        messages.success(request, f"USG Report {report.report_no} saved successfully.")
        return redirect("hms:usg_report_print", pk=report.pk)
    elif request.method == "POST" and is_ajax:
        return JsonResponse({"success": False, "error": "Please check the form for errors."}, status=400)

    return render(request, "hms/usg/usg_report_form.html", {
        "form":               form,
        "patient":            patient,
        "bill_item":          bill_item,
        "title":              "New USG Report",
        "findings_templates": json.dumps(USGReport.FINDINGS_TEMPLATES),
        "measurement_fields": USGReport.MEASUREMENT_FIELDS,
        "advice_quick_options": USG_ADVICE_QUICK_OPTIONS,
        "impression_groups": _usg_impression_groups(),
    })


@login_required
def usg_report_edit(request, pk):
    report = get_object_or_404(USGReport, pk=pk)
    form   = USGReportForm(request.POST or None, instance=report)
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    if request.method == "POST" and form.is_valid():
        form.save()
        if is_ajax:
            return JsonResponse({"success": True, "report_id": report.pk})
        messages.success(request, f"Report {report.report_no} updated.")
        return redirect("hms:usg_report_print", pk=report.pk)
    elif request.method == "POST" and is_ajax:
        return JsonResponse({"success": False, "error": "Please check the form for errors."}, status=400)

    return render(request, "hms/usg/usg_report_form.html", {
        "form":               form,
        "report":             report,
        "title":              f"Edit {report.report_no}",
        "findings_templates": json.dumps(USGReport.FINDINGS_TEMPLATES),
        "measurement_fields": USGReport.MEASUREMENT_FIELDS,
        "advice_quick_options": USG_ADVICE_QUICK_OPTIONS,
        "impression_groups": _usg_impression_groups(),
    })


@login_required
def usg_report_print(request, pk):
    """Render a print-ready USG report page."""
    report = get_object_or_404(
        USGReport.objects.select_related(
            "patient", "reporting_doctor", "referred_by", "consultation"
        ),
        pk=pk
    )
    return render(request, "hms/usg/usg_report_print.html", {
        "report": report,
    })


@login_required
def usg_report_pdf(request, pk):
    """Generate PDF of USG report via xhtml2pdf."""
    report = get_object_or_404(
        USGReport.objects.select_related(
            "patient", "reporting_doctor", "referred_by"
        ),
        pk=pk
    )
    return render_to_pdf("hms/usg/usg_report_print.html", {"report": report})


@login_required 
def usg_report_delete(request, pk):
    report = get_object_or_404(USGReport, pk=pk)
    if request.method == "POST":
        report.delete()
        messages.success(request, "USG Report deleted.")
        return redirect("hms:usg_report_list")
    return render(request, "hms/usg/usg_report_confirm_delete.html", {"report": report})

