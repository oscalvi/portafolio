"""Run a migration job synchronously in the foreground.

Useful for debugging the engine without a running qcluster:

    python manage.py run_job 3
"""
from django.core.management.base import BaseCommand, CommandError

from migration.models import MigrationJob
from migration.tasks import run_migration_task


class Command(BaseCommand):
    help = "Run a pending/failed migration job in this process."

    def add_arguments(self, parser):
        parser.add_argument("job_id", type=int)

    def handle(self, *args, **options):
        job_id = options["job_id"]
        try:
            job = MigrationJob.objects.get(pk=job_id)
        except MigrationJob.DoesNotExist:
            raise CommandError(f"No migration job with id {job_id}")

        self.stdout.write(f"Running job #{job.pk}: {job.source} -> {job.dest}")
        totals = run_migration_task(job.pk)
        self.stdout.write(self.style.SUCCESS(f"Done: {totals}"))
