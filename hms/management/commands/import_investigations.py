from django.core.management.base import BaseCommand
import pandas as pd

from hms.models import InvestigationCategory, Investigation


class Command(BaseCommand):
    help = "Import investigations from Excel (price.xls)"

    def handle(self, *args, **kwargs):
        file_path = "price.xls"  # file must be in project root

        df = pd.read_excel(file_path)

        # Default category (LABORATORY)
        category, _ = InvestigationCategory.objects.get_or_create(
            name="Laboratory"
        )

        count = 0

        for _, row in df.iterrows():
            name = str(row["Investigation Name"]).strip()
            price = float(row["Amount"])

            if not name or name.lower() == "nan":
                continue

            Investigation.objects.update_or_create(
                name=name,
                defaults={
                    "category": category,
                    "price": price,
                    "is_active": True,
                }
            )

            count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {count} investigations successfully"
            )
        )
