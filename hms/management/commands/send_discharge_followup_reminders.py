from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from hms.models import IPDAdmission
from hms.services.whatsapp import send_discharge_followup_reminder, WhatsAppSendError


class Command(BaseCommand):
    help = (
        "Send WhatsApp follow-up reminders to discharged IPD patients whose "
        "follow_up_date is N days ahead (default 1 -- i.e. tomorrow's "
        "follow-ups, meant to run once daily). Skips admissions that "
        "already have followup_reminder_sent_at set, so it's safe to run "
        "more than once."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days-ahead", type=int, default=1,
            help="How many days ahead to look for follow-up visits (default: 1).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="List which admissions would be reminded without sending or marking them.",
        )

    def handle(self, *args, **options):
        target_date = timezone.localdate() + timedelta(days=options["days_ahead"])

        admissions = IPDAdmission.objects.filter(
            follow_up_date=target_date,
            discharge_date__isnull=False,
            followup_reminder_sent_at__isnull=True,
        ).select_related("patient")

        if not admissions:
            self.stdout.write(f"No unreminded discharge follow-ups on {target_date}.")
            return

        if options["dry_run"]:
            for admission in admissions:
                self.stdout.write(
                    f"[DRY RUN] Would remind {admission.patient.full_name} -- follow-up on {admission.follow_up_date}"
                )
            self.stdout.write(f"{admissions.count()} admission(s) would be reminded.")
            return

        sent = failed = skipped = 0
        for admission in admissions:
            try:
                send_discharge_followup_reminder(admission)
            except ValueError as exc:
                self.stderr.write(self.style.WARNING(f"Skipped admission {admission.id} ({admission.patient}): {exc}"))
                skipped += 1
                continue
            except WhatsAppSendError as exc:
                self.stderr.write(self.style.ERROR(f"Failed admission {admission.id} ({admission.patient}): {exc}"))
                failed += 1
                continue

            admission.followup_reminder_sent_at = timezone.now()
            admission.save(update_fields=["followup_reminder_sent_at"])
            sent += 1

        self.stdout.write(self.style.SUCCESS(
            f"Follow-up reminders for {target_date}: {sent} sent, {failed} failed, {skipped} skipped (bad mobile)."
        ))
