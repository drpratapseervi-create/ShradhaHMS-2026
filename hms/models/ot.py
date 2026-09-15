from django.db import models

# ===================== OT =====================
class OTBooking(models.Model):
    patient     = models.ForeignKey("Patient", on_delete=models.CASCADE)
    uhid        = models.CharField(max_length=20)
    surgeon     = models.CharField(max_length=100)
    assistant   = models.CharField(max_length=100, blank=True, null=True)
    anesthetist = models.CharField(max_length=100)
    procedure   = models.CharField(max_length=200)
    ot_date     = models.DateField()
    ot_time     = models.TimeField()
    ot_room     = models.CharField(max_length=50)
    case_type   = models.CharField(
        max_length=20,
        choices=[("Elective", "Elective"), ("Emergency", "Emergency")]
    )
    anesthesia_type = models.CharField(
        max_length=20,
        choices=[("GA", "GA"), ("SA", "SA"), ("LA", "LA")]
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ("Scheduled",  "Scheduled"),
            ("Completed",  "Completed"),
            ("Cancelled",  "Cancelled"),
        ],
        default="Scheduled"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.patient} - {self.procedure}"


class OTNotes(models.Model):
    booking           = models.OneToOneField(OTBooking, on_delete=models.CASCADE)
    start_time        = models.TimeField()
    end_time          = models.TimeField()
    findings          = models.TextField()
    procedure_done    = models.TextField()
    complications     = models.TextField(blank=True, null=True)
    blood_loss        = models.CharField(max_length=50, blank=True)
    post_op_condition = models.TextField()
    created_at        = models.DateTimeField(auto_now_add=True)


