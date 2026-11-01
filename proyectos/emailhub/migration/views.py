from __future__ import annotations

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django_q.tasks import async_task

from .forms import AccountForm
from .imap_engine.client import verify_connection
from .imap_engine.migrate import list_folder_plans
from .models import FolderProgress, MailAccount, MigrationJob


def dashboard(request):
    jobs = MigrationJob.objects.select_related("source", "dest")
    return render(request, "migration/dashboard.html", {"jobs": jobs})


def _account_from_form(form: AccountForm, role: str) -> MailAccount:
    cd = form.cleaned_data
    account = MailAccount(
        label=cd.get("label", ""),
        role=role,
        host=cd["host"].strip(),
        port=cd["port"],
        use_ssl=cd["use_ssl"],
        username=cd["username"].strip(),
    )
    account.set_password(cd["password"])
    return account


def new_migration(request):
    src_form = AccountForm(request.POST or None, prefix="src")
    dst_form = AccountForm(request.POST or None, prefix="dst")

    if request.method == "POST":
        if not (src_form.is_valid() and dst_form.is_valid()):
            messages.error(request, "Please fix the errors below.")
        else:
            src_account = _account_from_form(src_form, MailAccount.SOURCE)
            dst_account = _account_from_form(dst_form, MailAccount.DESTINATION)

            ok, err = verify_connection(src_account.creds())
            if not ok:
                messages.error(request, f"Source login failed: {err}")
                return _render_new(request, src_form, dst_form)
            ok, err = verify_connection(dst_account.creds())
            if not ok:
                messages.error(request, f"Destination login failed: {err}")
                return _render_new(request, src_form, dst_form)

            try:
                plans = list_folder_plans(src_account.creds())
            except Exception as exc:  # noqa: BLE001
                messages.error(request, f"Could not list source folders: {exc}")
                return _render_new(request, src_form, dst_form)

            with transaction.atomic():
                src_account.save()
                dst_account.save()
                job = MigrationJob.objects.create(
                    source=src_account,
                    dest=dst_account,
                    mode=MigrationJob.ALL,
                    status=MigrationJob.PENDING,
                )
                FolderProgress.objects.bulk_create(
                    [
                        FolderProgress(
                            job=job,
                            source_path=p.source_path,
                            dest_path=p.dest_path,
                            selected=True,
                        )
                        for p in plans
                    ]
                )
            messages.success(
                request, "Connected. Choose what to move, then start the migration."
            )
            return redirect("job_detail", pk=job.pk)

    return _render_new(request, src_form, dst_form)


def _render_new(request, src_form, dst_form):
    return render(
        request,
        "migration/new_migration.html",
        {"src_form": src_form, "dst_form": dst_form},
    )


def job_detail(request, pk):
    job = get_object_or_404(
        MigrationJob.objects.select_related("source", "dest"), pk=pk
    )
    return render(request, "migration/job_detail.html", {"job": job})


@require_POST
def job_start(request, pk):
    job = get_object_or_404(MigrationJob, pk=pk)
    if job.status != MigrationJob.PENDING:
        messages.error(request, "This job has already been started.")
        return redirect("job_detail", pk=pk)

    mode = request.POST.get("mode", MigrationJob.ALL)
    job.mode = MigrationJob.SELECTED if mode == MigrationJob.SELECTED else MigrationJob.ALL

    if job.mode == MigrationJob.SELECTED:
        chosen = set(request.POST.getlist("folders"))
        for row in job.folders.all():
            row.selected = str(row.pk) in chosen
            row.save(update_fields=["selected"])
        if not chosen:
            messages.error(request, "Select at least one folder, or choose 'move everything'.")
            return redirect("job_detail", pk=pk)
    else:
        job.folders.update(selected=True)

    job.save(update_fields=["mode"])
    async_task("migration.tasks.run_migration_task", job.pk)
    messages.success(request, "Migration queued.")
    return redirect("job_detail", pk=pk)


@require_POST
def job_cancel(request, pk):
    job = get_object_or_404(MigrationJob, pk=pk)
    if job.is_running:
        MigrationJob.objects.filter(pk=pk, status__in=[MigrationJob.RUNNING]).update(
            status=MigrationJob.CANCELLING
        )
        messages.info(request, "Cancelling after the current folder batch...")
    return redirect("job_detail", pk=pk)


def job_progress(request, pk):
    job = get_object_or_404(
        MigrationJob.objects.select_related("source", "dest"), pk=pk
    )
    return render(request, "migration/_job_progress.html", {"job": job})
