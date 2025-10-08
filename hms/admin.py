from django.contrib import admin
from .models import Patient, Doctor, Appointment

@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('id','full_name','age','gender','phone')

@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ('id','full_name','specialization','op_fee')

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ('id','patient','doctor','date','time','purpose','created_at')
    list_filter = ('date','doctor')
