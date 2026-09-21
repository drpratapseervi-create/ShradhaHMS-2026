from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from hms.models import Appointment
from hms.services.whatsapp import send_appointment_reminder, WhatsAppSendError


class Command(BaseCommand):
    help = (
        "Send WhatsApp appointment reminders for Scheduled appointments N days "
        "ahead (default 1 -- i.e. tomorrow's appointments, meant to run once "
        "daily). Skips appointments that already have reminder_sent_at set, "
        "so it's safe to run more than once."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days-ahead", type=int, default=1,
            help="How many days ahead to look for appointments (default: 1).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="List which appointments would be reminded without sending or marking them.",
        )

    def handle(self, *args, **options):
        target_date = timezone.localdate() + timedelta(days=options["days_ahead"])

        appointments = Appointment.objects.filter(
            date=target_date,
            status="Scheduled",
            reminder_sent_at__isnull=True,
        ).select_related("patient", "doctor")

        if not appointments:
            self.stdout.write(f"No unreminded Scheduled appointments on {target_date}.")
            return

        if options["dry_run"]:
            for appt in appointments:
                self.stdout.write(f"[DRY RUN] Would remind {appt.patient.full_name} -- {appt.date} {appt.time}")
            self.stdout.write(f"{appointments.count()} appointment(s) would be reminded.")
            return

        sent = failed = skipped = 0
        for appt in appointments:
            try:
                send_appointment_reminder(appt)
            except ValueError as exc:
                self.stderr.write(self.style.WARNING(f"Skipped appointment {appt.id} ({appt.patient}): {exc}"))
                skipped += 1
                continue
            except WhatsAppSendError as exc:
                self.stderr.write(self.style.ERROR(f"Failed appointment {appt.id} ({appt.patient}): {exc}"))
                failed += 1
                continue

            appt.reminder_sent_at = timezone.now()
            appt.save(update_fields=["reminder_sent_at"])
            sent += 1

        self.stdout.write(self.style.SUCCESS(
            f"Reminders for {target_date}: {sent} sent, {failed} failed, {skipped} skipped (bad mobile)."
        ))
