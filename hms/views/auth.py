from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required

from ..decorators import role_required
from ..models import Appointment, Patient, Doctor, IPDAdmission, Bed


@login_required
def get_doctors(request):
    dept_id = request.GET.get("department_id")
    doctors = Doctor.objects.filter(department_id=dept_id).values("id", "full_name")
    return JsonResponse({"doctors": list(doctors)})


def get_user_role(user):
    if user.is_superuser:
        return "superadmin"
    groups = user.groups.values_list("name", flat=True)
    if "Admin" in groups:       return "admin"
    if "Doctor" in groups:      return "doctor"
    if "Nursing Staff" in groups: return "nursing"
    if "Laboratory" in groups:  return "laboratory"
    if "Reception" in groups:   return "reception"
    return "unknown"


def hms_login(request):
    if request.user.is_authenticated:
        return redirect_by_role(request.user)
    error = None
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user     = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect_by_role(user)
        else:
            error = "Invalid username or password."
    return render(request, "hms/login.html", {"error": error})


def redirect_by_role(user):
    role = get_user_role(user)
    redirects = {
        "superadmin": "/admin/",
        "admin":      "/admin/",
        "doctor":     "/dashboard/doctor/",
        "nursing":    "/dashboard/nursing/",
        "laboratory": "/lab/billing/",
        "reception":  "/dashboard/",
        "pharmacy":   "/pharmacy/",
    }
    return redirect(redirects.get(role, "/dashboard/"))


def hms_logout(request):
    logout(request)
    return redirect("/login/")


@login_required
def dashboard(request):
    from datetime import date as today_date
    today = today_date.today()
    role  = get_user_role(request.user)
    appointments = Appointment.objects.filter(
        date=today
    ).select_related("patient", "doctor", "consultation").order_by("time")
    return render(request, "dashboard.html", {
        "role":               role,
        "patient_count":      Patient.objects.count(),
        "doctor_count":       Doctor.objects.count(),
        "appt_count":         appointments.count(),
        "appointments":       appointments,
        "latest_appointment": appointments.filter(status="Scheduled").first(),
    })


@login_required
@role_required("doctor")
def doctor_dashboard(request):
    from datetime import date as today_date
    today = today_date.today()
    appointments = Appointment.objects.filter(
        date=today
    ).select_related("patient", "consultation").order_by("time")
    return render(request, "dashboard.html", {
        "appointments":       appointments,
        "appt_count":         appointments.count(),
        "latest_appointment": appointments.filter(status="Scheduled").first(),
    })


@login_required
@role_required("nursing")
def nursing_dashboard(request):
    admitted = IPDAdmission.objects.filter(
        status="ADMITTED"
    ).select_related("patient", "bed", "ward")
    beds = Bed.objects.all()
    return render(request, "dashboard.html", {
        "admitted_patients": admitted,
        "beds":              beds,
    })

