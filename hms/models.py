from django.db import models

class Patient(models.Model):
    full_name = models.CharField(max_length=120)
    age = models.PositiveIntegerField()
    gender = models.CharField(max_length=10, choices=[('Male','Male'),('Female','Female'),('Other','Other')])
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)

    def __str__(self):
        return f"{self.full_name} ({self.id})"

class Doctor(models.Model):
    full_name = models.CharField(max_length=120)
    specialization = models.CharField(max_length=120, blank=True)
    op_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    def __str__(self):
        return self.full_name

class Appointment(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    doctor = models.ForeignKey(Doctor, on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateField()
    time = models.TimeField()
    purpose = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Appt #{self.pk} - {self.patient} with {self.doctor} on {self.date}"
