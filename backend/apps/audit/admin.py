"""Read-only admin for the audit trail.

Registrars and ICT need to search it; nobody may edit it. The absence of add,
change and delete permissions here is a deliberate part of FR-RPT-04, not an
oversight.
"""

from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = [
        "created_at",
        "actor_display",
        "action",
        "object_repr",
        "field_name",
        "change_display",
        "request_id",
    ]
    list_filter = ["action", "created_at", "content_type", "actor_role"]
    search_fields = [
        "object_repr",
        "field_name",
        "actor_name",
        "old_value",
        "new_value",
        "reason",
        "request_id",
    ]
    date_hierarchy = "created_at"
    list_select_related = ["actor", "content_type"]
    list_per_page = 50

    readonly_fields = [
        "created_at",
        "actor",
        "actor_name",
        "actor_role",
        "action",
        "content_type",
        "object_id",
        "object_repr",
        "field_name",
        "old_value",
        "new_value",
        "description",
        "reason",
        "ip_address",
        "user_agent",
        "request_id",
        "prev_hash",
        "row_hash",
    ]

    @admin.display(description=_("actor"), ordering="actor_name")
    def actor_display(self, obj: AuditLog) -> str:
        if obj.actor_role:
            return f"{obj.actor_name} ({obj.actor_role})"
        return obj.actor_name or "system"

    @admin.display(description=_("change"))
    def change_display(self, obj: AuditLog) -> str:
        if not obj.field_name:
            return obj.description
        return format_html(
            "<code>{}</code> → <code>{}</code>",
            "∅" if obj.old_value is None else obj.old_value,
            "∅" if obj.new_value is None else obj.new_value,
        )

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
