from django import forms
from .models import Admission, ChargeItem, AdvancePayment, FinalBill

class AdmissionForm(forms.ModelForm):
    class Meta:
        model = Admission
        fields = ["patient_name","mrn","reg_no","ward","bed","category","doctor","admit_at","discharge_at","remarks"]
        widgets = {
            "admit_at": forms.DateTimeInput(attrs={"type":"datetime-local"}),
            "discharge_at": forms.DateTimeInput(attrs={"type":"datetime-local"}),
        }

class ChargeItemForm(forms.ModelForm):
    class Meta:
        model = ChargeItem
        fields = ["date","type","particulars","qty","rate","sac_code"]
        widgets = {
            "date": forms.DateInput(attrs={"type":"date"})
        }

class AdvanceForm(forms.ModelForm):
    class Meta:
        model = AdvancePayment
        fields = ["date","amount","receipt_no","notes"]
        widgets = {"date": forms.DateInput(attrs={"type":"date"})}

class FinalBillForm(forms.ModelForm):
    class Meta:
        model = FinalBill
        fields = ["bill_no","discount","cgst","sgst","notes"]
