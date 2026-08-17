from __future__ import annotations

from rest_framework import serializers

from apps.audit.models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    entity = serializers.SerializerMethodField()
    actor_display = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "created_at",
            "action",
            "entity",
            "object_id",
            "object_repr",
            "field_name",
            "old_value",
            "new_value",
            "description",
            "reason",
            "actor_display",
            "actor_role",
            "request_id",
        ]
        read_only_fields = fields

    def get_entity(self, obj: AuditLog) -> str:
        if obj.content_type_id is None:
            return ""
        return f"{obj.content_type.app_label}.{obj.content_type.model}"

    def get_actor_display(self, obj: AuditLog) -> str:
        return obj.actor_name or "system"


class ChainVerificationSerializer(serializers.Serializer):
    ok = serializers.BooleanField(read_only=True)
    checked = serializers.IntegerField(read_only=True)
    first_broken_id = serializers.IntegerField(read_only=True, allow_null=True)
    detail = serializers.CharField(read_only=True)
