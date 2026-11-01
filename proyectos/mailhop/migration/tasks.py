"""Background task run by django-q2 (`manage.py qcluster`)."""
from __future__ import annotations

from django.db.models import Sum
from django.utils import timezone

from .imap_engine.migrate import Callbacks, FolderPlan, run_migration
from .models import FolderProgress, MigrationJob


def run_migration_task(job_id: int) -> dict:
    job = MigrationJob.objects.select_related("source", "dest").get(pk=job_id)

    job.status = MigrationJob.RUNNING
    job.started_at = timezone.now()
    job.error = ""
    job.save(update_fields=["status", "started_at", "error"])

    rows = list(job.folders.all())
    if job.mode == MigrationJob.SELECTED:
        rows = [r for r in rows if r.selected]

    by_source = {r.source_path: r for r in rows}
    plans = [FolderPlan(r.source_path, r.dest_path, r.selected) for r in rows]
    checkpoints = {r.source_path: r.last_uid for r in rows if r.last_uid}

    def folder_start(source_path, dest_path, total):
        row = by_source.get(source_path)
        if not row:
            return
        row.status = FolderProgress.RUNNING
        row.dest_path = dest_path
        row.total_messages = total
        row.save(update_fields=["status", "dest_path", "total_messages"])
        _recalc(job)

    def progress(source_path, last_uid, copied, skipped, failed):
        row = by_source.get(source_path)
        if not row:
            return
        row.last_uid = last_uid
        row.copied_messages = copied
        row.skipped_messages = skipped
        row.failed_messages = failed
        row.save(
            update_fields=[
                "last_uid",
                "copied_messages",
                "skipped_messages",
                "failed_messages",
            ]
        )
        _recalc(job)

    def folder_done(source_path, copied, skipped, failed):
        row = by_source.get(source_path)
        if not row:
            return
        row.status = FolderProgress.DONE
        row.copied_messages = copied
        row.skipped_messages = skipped
        row.failed_messages = failed
        row.save(
            update_fields=[
                "status",
                "copied_messages",
                "skipped_messages",
                "failed_messages",
            ]
        )
        _recalc(job)

    def should_cancel():
        return MigrationJob.objects.filter(
            pk=job_id, status=MigrationJob.CANCELLING
        ).exists()

    callbacks = Callbacks(folder_start, progress, folder_done, should_cancel)

    try:
        totals = run_migration(
            job.source.creds(), job.dest.creds(), plans, checkpoints, callbacks
        )
    except Exception as exc:  # noqa: BLE001
        MigrationJob.objects.filter(pk=job_id).update(
            status=MigrationJob.FAILED,
            error=f"{type(exc).__name__}: {exc}",
            finished_at=timezone.now(),
        )
        raise

    _recalc(job)
    cancelled = MigrationJob.objects.filter(
        pk=job_id, status=MigrationJob.CANCELLING
    ).exists()
    MigrationJob.objects.filter(pk=job_id).update(
        status=MigrationJob.CANCELLED if cancelled else MigrationJob.COMPLETED,
        finished_at=timezone.now(),
    )
    return totals


def _recalc(job: MigrationJob) -> None:
    agg = job.folders.aggregate(
        total=Sum("total_messages"),
        copied=Sum("copied_messages"),
        skipped=Sum("skipped_messages"),
        failed=Sum("failed_messages"),
    )
    MigrationJob.objects.filter(pk=job.pk).update(
        total_messages=agg["total"] or 0,
        copied_messages=agg["copied"] or 0,
        skipped_messages=agg["skipped"] or 0,
        failed_messages=agg["failed"] or 0,
    )
