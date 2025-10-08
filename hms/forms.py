from django import forms
from .models import Patient, Doctor, Appointment

class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = ['full_name','age','gender','phone','address']

class AppointmentForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ['patient','doctor','date','time','purpose']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'time': forms.TimeInput(attrs={'type': 'time'}),
        }
