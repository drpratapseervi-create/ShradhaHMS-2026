from django.db import models
from .core import Department, atc_code_validator

# ===================== SYMPTOM =====================
class Symptom(models.Model):
    name       = models.CharField(max_length=200)
    department = models.ForeignKey(
        Department, on_delete=models.CASCADE, related_name="symptoms"
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=9999, blank=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


# ===================== SIGN =====================
class Sign(models.Model):
    name       = models.CharField(max_length=200)
    department = models.ForeignKey(
        Department, on_delete=models.CASCADE, related_name="signs"
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=9999, blank=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


# ===================== PAST HISTORY =====================
class PastHistory(models.Model):
    name      = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


# ===================== SURGICAL HISTORY =====================
class SurgicalHistory(models.Model):
    name      = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


# ===================== ADVICE OPTION =====================
class AdviceOption(models.Model):
    text       = models.CharField(max_length=200)
    is_active  = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.text


# ===================== DIET ADVICE OPTION =====================
class DietAdviceOption(models.Model):
    text       = models.CharField(max_length=200)
    is_active  = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.text


# ===================== FOLLOW-UP NOTE PHRASE =====================
class FollowUpNotePhrase(models.Model):
    text       = models.CharField(max_length=200)
    is_active  = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.text

    # ===================== PRESCRIPTION TEMPLATE =====================
class PrescriptionTemplate(models.Model):
    name       = models.CharField(max_length=100, unique=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name

class PrescriptionTemplateItem(models.Model):
    template     = models.ForeignKey(PrescriptionTemplate, on_delete=models.CASCADE, related_name='items')
    medicine     = models.CharField(max_length=150)
    dose         = models.CharField(max_length=50,  blank=True)
    frequency    = models.CharField(max_length=50,  blank=True)
    duration     = models.CharField(max_length=50,  blank=True)
    instructions = models.CharField(max_length=100, blank=True)
    order        = models.PositiveSmallIntegerField(default=0)
    class Meta: ordering = ['order']

class VillageMaster(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class DrugMaster(models.Model):
    name         = models.CharField(max_length=150)
    generic_name = models.CharField(max_length=150, blank=True, default="")
    strength     = models.CharField(max_length=50,  blank=True, default="")
    category     = models.CharField(max_length=100, blank=True, default="")
    atc_code     = models.CharField(max_length=10, blank=True, default="",
                       validators=[atc_code_validator],
                       help_text="WHO ATC code e.g. 'N02BE01' for Paracetamol")
    is_active    = models.BooleanField(default=True)
    sort_order   = models.IntegerField(default=99)
    default_dose         = models.CharField(max_length=50,  blank=True, default="")
    default_frequency    = models.CharField(max_length=50,  blank=True, default="")
    default_duration     = models.CharField(max_length=50,  blank=True, default="")
    default_instructions = models.CharField(max_length=100, blank=True, default="")
    def __str__(self): return self.name


