import os
import pandas as pd

from django.conf import settings
from django.core.management.base import BaseCommand
from hms.models import ICDCode


class Command(BaseCommand):
    help = "Import ICD-10 codes from Excel file"

    def handle(self, *args, **options):
        file_path = os.path.join(settings.BASE_DIR, "ICD_codes.xlsx")

        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f"File not found: {file_path}"))
            return

        df = pd.read_excel(file_path, header=None)

        total = len(df)
        created = 0
        skipped = 0

        self.stdout.write(f"Starting ICD import… Total rows: {total}")

        for index, row in df.iterrows():
            code = str(row[0]).strip()
            description = str(row[1]).strip()

            if not code or code.lower() == "nan":
                continue

            _, is_created = ICDCode.objects.get_or_create(
                code=code,
                defaults={"description": description}
            )

            if is_created:
                created += 1
            else:
                skipped += 1

            # 🔑 Progress every 500 rows
            if index % 500 == 0 and index > 0:
                self.stdout.write(f"Processed {index}/{total} rows…")

        self.stdout.write(
            self.style.SUCCESS(
                f"ICD import finished | Added: {created} | Skipped: {skipped}"
            )
        )
