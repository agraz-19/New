"""
Django management command to migrate historical QPRRecord data to Snapshots.
Phase 6: Migrate quarterly QPRRecords to QuarterlySnapshot models.

Usage: python manage.py migrate_qpr_to_snapshots --dry-run  # Preview changes
       python manage.py migrate_qpr_to_snapshots               # Execute migration
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import date
from website.models import (
    QPRRecord, QuarterlySnapshot, WeeklySnapshot, MonthlySnapshot,
    WeeklyFill, MonthlyFill, QuarterlyFill
)
from website.views import NUMERIC_KEYS


class Command(BaseCommand):
    help = 'Migrate historical QPRRecord quarterly data to QuarterlySnapshot models'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without modifying database',
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Migrate only for specific user ID',
        )
        parser.add_argument(
            '--quarter',
            type=str,
            help='Migrate only specific quarter (e.g., Q1)',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        user_id = options.get('user_id')
        quarter = options.get('quarter')

        self.stdout.write('\n' + '='*70)
        self.stdout.write('HISTORICAL DATA MIGRATION: QPRRecord → Snapshots')
        self.stdout.write('='*70 + '\n')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE: No changes will be made\n'))
        
        # Find all quarterly QPRRecords to migrate
        query = QPRRecord.objects.filter(
            frequency__iexact='quarterly',
            is_submitted=True
        ).select_related('user')

        if user_id:
            query = query.filter(user_id=user_id)
            self.stdout.write(f'Filtering for user_id={user_id}')

        if quarter:
            query = query.filter(quarter=quarter)
            self.stdout.write(f'Filtering for quarter={quarter}')

        records_to_migrate = list(query)
        self.stdout.write(f'\nFound {len(records_to_migrate)} quaternary QPRRecords to migrate\n')

        if not records_to_migrate:
            self.stdout.write(self.style.SUCCESS('No records to migrate.'))
            return

        migrated = 0
        skipped = 0
        errors = 0

        for qpr in records_to_migrate:
            try:
                # Get or create snapshot
                snapshot, created = QuarterlySnapshot.objects.get_or_create(
                    user=qpr.user,
                    quarter=qpr.quarter or 'Q1',
                    year=qpr.year or 'N/A',
                    defaults={
                        'period_start': qpr.period_start,
                        'period_end': qpr.period_end,
                        'is_overwritten': False  # Legacy data, not manually edited
                    }
                )

                # Copy all numeric fields from QPRRecord to Snapshot
                for key in NUMERIC_KEYS:
                    value = getattr(qpr, key, None) or 0
                    try:
                        value = int(value) if value else 0
                    except (ValueError, TypeError):
                        value = 0
                    setattr(snapshot, key, value)

                if not dry_run:
                    snapshot.save()

                status = '[MIGRATED]' if created else '[UPDATED]'
                self.stdout.write(
                    f'{status} Q{snapshot.quarter} {snapshot.year} for user {qpr.user.id} '
                    f'({qpr.period_start} → {qpr.period_end})'
                )
                migrated += 1

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'[ERROR] Failed to migrate Q{qpr.quarter} {qpr.year} for user {qpr.user.id}: {str(e)}'
                    )
                )
                errors += 1

        # Migration complete - show summary
        self.stdout.write('\n' + '='*70)
        self.stdout.write(self.style.SUCCESS(f'\nMIGRATION SUMMARY'))
        self.stdout.write(f'  Migrated: {migrated}')
        self.stdout.write(f'  Errors: {errors}')
        self.stdout.write(f'  Mode: {"DRY RUN (no changes)" if dry_run else "EXECUTED"}')

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    '\n⚠️  DRY RUN COMPLETED\n'
                    'To execute the migration, run without --dry-run flag:\n'
                    '  python manage.py migrate_qpr_to_snapshots'
                )
            )

        self.stdout.write('='*70 + '\n')

        if errors > 0:
            raise CommandError(f'Migration completed with {errors} error(s)')
