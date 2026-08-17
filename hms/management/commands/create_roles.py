# hms/management/commands/create_roles.py

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission


class Command(BaseCommand):
    help = "Create default HMS roles with permissions"

    def handle(self, *args, **kwargs):

        # ── ADMIN ──────────────────────────────────────────────────
        admin_group, _ = Group.objects.get_or_create(name="Admin")
        self.stdout.write(self.style.SUCCESS("[OK] Admin role created"))

        # ── RECEPTION ──────────────────────────────────────────────
        reception, _ = Group.objects.get_or_create(name="Reception")
        reception_perms = [
            "add_patient", "change_patient", "view_patient",
            "add_appointment", "change_appointment", "view_appointment",
            "add_consultation", "view_consultation",
            "add_procedurebill", "view_procedurebill",
            "view_doctor", "view_department",
        ]
        assign_perms(reception, reception_perms)
        self.stdout.write(self.style.SUCCESS("[OK] Reception role created"))

        # ── DOCTOR ─────────────────────────────────────────────────
        doctor, _ = Group.objects.get_or_create(name="Doctor")
        doctor_perms = [
            "view_patient", "change_patient",
            "view_appointment", "change_appointment",
            "add_consultation", "change_consultation", "view_consultation",
            "view_investigation", "view_investigationresult",
            "add_dischargebill", "change_dischargebill", "view_dischargebill",
            "view_procedurebill",
        ]
        assign_perms(doctor, doctor_perms)
        self.stdout.write(self.style.SUCCESS("[OK] Doctor role created"))

        # ── NURSING STAFF ──────────────────────────────────────────
        nursing, _ = Group.objects.get_or_create(name="Nursing Staff")
        nursing_perms = [
            "view_patient", "change_patient",
            "view_appointment",
            "view_consultation",
            "add_investigationresult", "change_investigationresult", "view_investigationresult",
            "view_bed", "change_bed",
            "view_procedurebill",
        ]
        assign_perms(nursing, nursing_perms)
        self.stdout.write(self.style.SUCCESS("[OK] Nursing Staff role created"))

        # ── LABORATORY ─────────────────────────────────────────────
        laboratory, _ = Group.objects.get_or_create(name="Laboratory")
        laboratory_perms = [
            "view_patient",
            "add_investigation", "change_investigation", "view_investigation",
            "add_investigationresult", "change_investigationresult", "view_investigationresult",
            "add_investigationparameter", "change_investigationparameter", "view_investigationparameter",
        ]
        assign_perms(laboratory, laboratory_perms)
        self.stdout.write(self.style.SUCCESS("[OK] Laboratory role created"))

        self.stdout.write(self.style.SUCCESS("\n[DONE] All HMS roles created successfully!"))


def assign_perms(group, codenames):
    """Assign permissions to a group by codename, silently skip missing ones."""
    for codename in codenames:
        try:
            perm = Permission.objects.get(codename=codename)
            group.permissions.add(perm)
        except Permission.DoesNotExist:
            pass