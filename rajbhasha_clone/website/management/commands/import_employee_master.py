from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

import openpyxl

from website.models import EmployeeMaster


def _clean_text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _clean_empcode(value):
    raw = _clean_text(value).replace(".0", "")
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _row_value(row, header_map, column_name):
    idx = header_map.get(column_name)
    if idx is None:
        return None
    return row[idx]


class Command(BaseCommand):
    help = "Import employee master data from the TG HOD officers Excel sheet into the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            default=str(Path(settings.MEDIA_ROOT) / "data" / "tg_hod_officers_employee_report.xlsx"),
            help="Path to the Excel file to import.",
        )
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Delete existing employee master rows before importing.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        file_path = Path(options["file"])
        replace = options["replace"]

        if not file_path.exists():
            raise CommandError(f"Excel file not found: {file_path}")

        workbook = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        worksheet = workbook.active

        rows = worksheet.iter_rows(values_only=True)
        headers = next(rows, None)
        if not headers:
            raise CommandError("The provided Excel sheet is empty.")

        header_map = {str(header).strip(): idx for idx, header in enumerate(headers) if header is not None}
        required_headers = ["Empcode", "Name", "Name in Hindi", "Designation", "State", "Mobile", "IP Number"]
        missing_headers = [header for header in required_headers if header not in header_map]
        if missing_headers:
            raise CommandError(f"Missing required columns: {', '.join(missing_headers)}")

        if replace:
            deleted_count, _ = EmployeeMaster.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Deleted {deleted_count} existing employee master rows."))

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for row in rows:
            empcode = _clean_empcode(row[header_map["Empcode"]])
            if empcode is None:
                skipped_count += 1
                continue

            defaults = {
                "name": _clean_text(_row_value(row, header_map, "Name")),
                "hindi_name": _clean_text(_row_value(row, header_map, "Name in Hindi")),
                "designation": _clean_text(_row_value(row, header_map, "Designation")),
                "state": _clean_text(_row_value(row, header_map, "State")),
                "mobile": _clean_text(_row_value(row, header_map, "Mobile")),
                "ip_number": _clean_text(_row_value(row, header_map, "IP Number")),
                "emergency_contact": _clean_text(_row_value(row, header_map, "Emergency Contact")),
                "division": _clean_text(_row_value(row, header_map, "Division")),
                "is_active": True,
                "transferred_at": None,
            }

            _, created = EmployeeMaster.objects.update_or_create(
                empcode=empcode,
                defaults=defaults,
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        workbook.close()

        self.stdout.write(
            self.style.SUCCESS(
                f"Employee master import completed. Created: {created_count}, Updated: {updated_count}, Skipped: {skipped_count}"
            )
        )
