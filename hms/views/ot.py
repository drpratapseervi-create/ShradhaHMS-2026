from datetime import date

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required

from ..models import OTBooking, OTNotes, Doctor


@login_required
def ot_dashboard(request):
    today = date.today()
    ot_list = OTBooking.objects.filter(ot_date=today).order_by("ot_time")
    return render(request, "ot/dashboard.html", {"ot_list": ot_list})


@login_required
def ot_create(request):
    if request.method == "POST":
        OTBooking.objects.create(
            patient_id=request.POST.get("patient"),
            uhid=request.POST.get("uhid"),
            surgeon=request.POST.get("surgeon"),
            assistant=request.POST.get("assistant"),
            anesthetist=request.POST.get("anesthetist"),
            procedure=request.POST.get("procedure"),
            ot_date=request.POST.get("ot_date"),
            ot_time=request.POST.get("ot_time"),
            ot_room=request.POST.get("ot_room"),
            case_type=request.POST.get("case_type"),
            anesthesia_type=request.POST.get("anesthesia_type"),
        )
        return redirect("hms:ot_dashboard")

    context = {
        "surgeons": Doctor.objects.filter(is_surgeon=True).order_by("full_name"),
        "assistants": Doctor.objects.filter(is_assistant=True).order_by("full_name"),
        "anesthetists": Doctor.objects.filter(is_anesthetist=True).order_by("full_name"),
    }
    return render(request, "ot/ot_form.html", context)


@login_required
def ot_detail(request, id):
    booking = get_object_or_404(OTBooking, id=id)
    return render(request, "ot/ot_detail.html", {"booking": booking})


@login_required
def ot_edit(request, id):
    booking = get_object_or_404(OTBooking, id=id)
    surgeons = Doctor.objects.filter(is_surgeon=True).order_by("full_name")
    assistants = Doctor.objects.filter(is_assistant=True).order_by("full_name")
    anesthetists = Doctor.objects.filter(is_anesthetist=True).order_by("full_name")

    if request.method == "POST":
        booking.surgeon        = request.POST.get("surgeon")
        booking.assistant      = request.POST.get("assistant")
        booking.anesthetist    = request.POST.get("anesthetist")
        booking.procedure      = request.POST.get("procedure")
        booking.ot_date        = request.POST.get("ot_date")
        booking.ot_time        = request.POST.get("ot_time")
        booking.ot_room        = request.POST.get("ot_room")
        booking.case_type      = request.POST.get("case_type")
        booking.anesthesia_type = request.POST.get("anesthesia_type")
        booking.save()
        return redirect("hms:ot_detail", id=id)

    return render(request, "ot/ot_edit.html", {
        "booking": booking,
        "surgeons": surgeons,
        "assistants": assistants,
        "anesthetists": anesthetists,
    })


@login_required
def ot_cancel(request, id):
    booking = get_object_or_404(OTBooking, id=id)
    if request.method == "POST":
        booking.status = "Cancelled"
        booking.save()
        return redirect("hms:ot_dashboard")
    return render(request, "ot/ot_confirm_cancel.html", {"booking": booking})


@login_required
def ot_status_update(request, id):
    booking = get_object_or_404(OTBooking, id=id)
    if request.method == "POST":
        new_status = request.POST.get("status")
        if new_status in ["Scheduled", "Completed", "Cancelled"]:
            booking.status = new_status
            booking.save()
    return redirect("hms:ot_dashboard")


@login_required
def ot_notes(request, id):
    booking = get_object_or_404(OTBooking, id=id)
    
    # ← use filter().first() instead of get_or_create
    notes = OTNotes.objects.filter(booking=booking).first()

    if request.method == "POST":
        if notes is None:
            notes = OTNotes(booking=booking)
        notes.start_time        = request.POST.get("start_time")
        notes.end_time          = request.POST.get("end_time")
        notes.findings          = request.POST.get("findings")
        notes.procedure_done    = request.POST.get("procedure_done")
        notes.complications     = request.POST.get("complications")
        notes.blood_loss        = request.POST.get("blood_loss")
        notes.post_op_condition = request.POST.get("post_op_condition")
        notes.save()
        booking.status = "Completed"
        booking.save()
        return redirect("hms:ot_detail", id=id)

    return render(request, "ot/ot_notes.html", {"booking": booking, "notes": notes})


@login_required
def ot_print(request, id):
    booking = get_object_or_404(OTBooking, id=id)
    notes = OTNotes.objects.filter(booking=booking).first()
    return render(request, "ot/ot_print.html", {"booking": booking, "notes": notes})

    from ..models import InventoryItem, StockIn, StockOut, Supplier

