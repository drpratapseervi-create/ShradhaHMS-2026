from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

# ===================== USER PROFILE =====================
class UserProfile(models.Model):
    ROLE_CHOICES = [
        ("admin",      "Admin"),
        ("doctor",     "Doctor"),
        ("nursing",    "Nursing Staff"),
        ("laboratory", "Laboratory"),
        ("reception",  "Reception"),
        ("pharmacy",   "Pharmacy"),
    ]

    user      = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role      = models.CharField(max_length=20, choices=ROLE_CHOICES, default="reception")
    full_name = models.CharField(max_length=100, blank=True)
    phone     = models.CharField(max_length=15, blank=True)
    is_active = models.BooleanField(default=True)
    doctor    = models.OneToOneField(
        "Doctor", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="user_profile"
    )

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

    class Meta:
        verbose_name        = "User Profile"
        verbose_name_plural = "User Profiles"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()


# ===================== EXPENSE =====================
class Expense(models.Model):
    date    = models.DateField(auto_now_add=True)
    title   = models.CharField(max_length=200)
    amount  = models.DecimalField(max_digits=10, decimal_places=2)
    remarks = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.title

