from __future__ import annotations

from django.db import models


class MailAccount(models.Model):
    SOURCE = "source"
    DESTINATION = "destination"
    ROLE_CHOICES = [(SOURCE, "Source"), (DESTINATION, "Destination")]

    label = models.CharField(max_length=200, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    host = models.CharField(max_length=255)
    port = models.PositiveIntegerField(default=993)
    use_ssl = models.BooleanField(default=True)
    username = models.CharField(max_length=255)
    secret_encrypted = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.label or self.username} ({self.role})"

    def set_password(self, raw: str) -> None:
        from .crypto import encrypt

        self.secret_encrypted = encrypt(raw)

    def get_password(self) -> str:
        from .crypto import decrypt

        return decrypt(self.secret_encrypted)

    def creds(self):
        from .imap_engine.client import ImapCreds

        return ImapCreds(
            host=self.host,
            port=int(self.port),
            use_ssl=self.use_ssl,
            username=self.username,
            password=self.get_password(),
        )


class MigrationJob(models.Model):
    PENDING = "pending"
    RUNNING = "running"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (RUNNING, "Running"),
        (CANCELLING, "Cancelling"),
        (COMPLETED, "Completed"),
        (FAILED, "Failed"),
        (CANCELLED, "Cancelled"),
    ]

    ALL = "all"
    SELECTED = "selected"
    MODE_CHOICES = [(ALL, "Move everything"), (SELECTED, "Selected folders")]

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default=ALL)
    source = models.ForeignKey(
        MailAccount, on_delete=models.CASCADE, related_name="source_jobs"
    )
    dest = models.ForeignKey(
        MailAccount, on_delete=models.CASCADE, related_name="dest_jobs"
    )

    total_messages = models.IntegerField(default=0)
    copied_messages = models.IntegerField(default=0)
    skipped_messages = models.IntegerField(default=0)
    failed_messages = models.IntegerField(default=0)
    error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Job #{self.pk}: {self.source.username} -> {self.dest.username}"

    @property
    def is_terminal(self) -> bool:
        return self.status in (self.COMPLETED, self.FAILED, self.CANCELLED)

    @property
    def is_running(self) -> bool:
        return self.status in (self.RUNNING, self.CANCELLING)

    @property
    def percent(self) -> int:
        if not self.total_messages:
            return 0
        done = self.copied_messages + self.skipped_messages
        return min(100, round(100 * done / self.total_messages))


class FolderProgress(models.Model):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"

    job = models.ForeignKey(
        MigrationJob, on_delete=models.CASCADE, related_name="folders"
    )
    source_path = models.CharField(max_length=1024)
    dest_path = models.CharField(max_length=1024)
    selected = models.BooleanField(default=True)
    status = models.CharField(max_length=20, default=PENDING)

    total_messages = models.IntegerField(default=0)
    copied_messages = models.IntegerField(default=0)
    skipped_messages = models.IntegerField(default=0)
    failed_messages = models.IntegerField(default=0)
    last_uid = models.BigIntegerField(default=0)
    error = models.TextField(blank=True)

    class Meta:
        unique_together = [("job", "source_path")]
        ordering = ["source_path"]

    def __str__(self) -> str:
        return f"{self.source_path} -> {self.dest_path}"
