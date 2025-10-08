from django.shortcuts import render, redirect, get_object_or_404
from .models import Patient, Doctor, Appointment
from .forms import PatientForm, AppointmentForm

def dashboard(request):
    context = {
        'patient_count': Patient.objects.count(),
        'doctor_count': Doctor.objects.count(),
        'appt_count': Appointment.objects.count(),
    }
    return render(request, 'dashboard.html', context)

def patient_create(request):
    form = PatientForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('dashboard')
    return render(request, 'patient_form.html', {'form': form})

def appointment_create(request):
    form = AppointmentForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        appt = form.save()
        return redirect('print_opd', appointment_id=appt.id)
    return render(request, 'appointment_form.html', {'form': form})

def print_opd(request, appointment_id):
    appt = get_object_or_404(Appointment, id=appointment_id)
    fee = float(appt.doctor.op_fee) if appt.doctor else 0.0
    ctx = {
        'receipt_no': appt.id,
        'date': appt.date.strftime('%d-%m-%Y'),
        'visit_no': appt.id,
        'uhid': appt.patient.id,
        'patient_name': appt.patient.full_name,
        'age': appt.patient.age,
        'gender': appt.patient.gender,
        'doctor_name': appt.doctor.full_name if appt.doctor else '—',
        'fee': f'{fee:.2f}',
        'purpose': appt.purpose or 'OPD Consultation',
        'created_at': appt.created_at,
    }
    return render(request, 'opd_receipt_a4.html', ctx)
