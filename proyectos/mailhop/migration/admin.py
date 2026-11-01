from django.contrib import admin

from .models import FolderProgress, MailAccount, MigrationJob


@admin.register(MailAccount)
class MailAccountAdmin(admin.ModelAdmin):
    list_display = ("id", "label", "role", "host", "username", "created_at")
    list_filter = ("role", "use_ssl")
    search_fields = ("label", "host", "username")
    exclude = ("secret_encrypted",)

    def has_add_permission(self, request):  # accounts are created via the app flow
        return False


class FolderProgressInline(admin.TabularInline):
    model = FolderProgress
    extra = 0
    readonly_fields = (
        "source_path",
        "dest_path",
        "status",
        "total_messages",
        "copied_messages",
        "skipped_messages",
        "failed_messages",
        "last_uid",
    )
    can_delete = False


@admin.register(MigrationJob)
class MigrationJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "status",
        "mode",
        "source",
        "dest",
        "percent",
        "total_messages",
        "created_at",
    )
    list_filter = ("status", "mode")
    inlines = [FolderProgressInline]
