"""Admin for the sync ledger and ID sequences — operational tooling for ICT."""

from __future__ import annotations

from django.contrib import admin, messages
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import ConflictResolution, IdSequence, SyncConflict, SyncOperation


@admin.register(IdSequence)
class IdSequenceAdmin(admin.ModelAdmin):
    list_display = ["scope", "last_value", "updated_at"]
    search_fields = ["scope"]
    readonly_fields = ["updated_at"]

    def has_add_permission(self, request) -> bool:
        # Sequences are created by the code that allocates from them; a
        # hand-made row is how you end up issuing a duplicate student ID.
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        # Deleting a counter would let already-issued identifiers be reissued,
        # breaching FR-REG-01's non-reusability.
        return False


@admin.register(SyncOperation)
class SyncOperationAdmin(admin.ModelAdmin):
    list_display = [
        "client_op_id",
        "entity",
        "action",
        "status",
        "submitted_by",
        "device_id",
        "client_timestamp",
        "received_at",
    ]
    list_filter = ["status", "entity", "action", "received_at"]
    search_fields = ["client_op_id", "device_id", "submitted_by__email"]
    readonly_fields = [
        "client_op_id",
        "entity",
        "action",
        "payload",
        "client_timestamp",
        "received_at",
        "status",
        "result",
        "error_detail",
        "submitted_by",
        "device_id",
        "target_content_type",
        "target_object_id",
    ]
    date_hierarchy = "received_at"

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        # The ledger is the record of what devices sent. Editing it would break
        # replay protection.
        return False


@admin.register(SyncConflict)
class SyncConflictAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "entity",
        "field_name",
        "server_value",
        "client_value",
        "status",
        "created_at",
        "resolved_by",
    ]
    list_filter = ["status", "entity", "created_at"]
    search_fields = ["entity", "field_name", "resolution_reason"]
    readonly_fields = [
        "sync_operation",
        "entity",
        "field_name",
        "server_value",
        "client_value",
        "server_updated_at",
        "client_timestamp",
        "target_content_type",
        "target_object_id",
        "created_at",
        "resolved_by",
        "resolved_at",
    ]
    fields = [*readonly_fields, "status", "resolution_reason"]
    actions = ["keep_server_value", "accept_client_value"]

    def has_add_permission(self, request) -> bool:
        return False

    def save_model(self, request, obj, form, change) -> None:
        if obj.status != ConflictResolution.OPEN and not obj.resolution_reason.strip():
            messages.error(request, _("Give a reason when resolving a conflict."))
            return
        if obj.status != ConflictResolution.OPEN and obj.resolved_at is None:
            obj.resolved_by = request.user
            obj.resolved_at = timezone.now()
        super().save_model(request, obj, form, change)

    @admin.action(description=_("Keep the server value"))
    def keep_server_value(self, request, queryset) -> None:
        updated = self._resolve(request, queryset, ConflictResolution.RESOLVED_SERVER)
        messages.success(request, _("%(n)d conflict(s) resolved.") % {"n": updated})

    @admin.action(description=_("Accept the client value (records an overwrite)"))
    def accept_client_value(self, request, queryset) -> None:
        updated = self._resolve(request, queryset, ConflictResolution.RESOLVED_CLIENT)
        messages.success(request, _("%(n)d conflict(s) resolved.") % {"n": updated})

    def _resolve(self, request, queryset, resolution: str) -> int:
        return queryset.filter(status=ConflictResolution.OPEN).update(
            status=resolution,
            resolved_by=request.user,
            resolved_at=timezone.now(),
            resolution_reason=_("Resolved from the admin bulk action."),
        )
