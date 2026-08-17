"""Serializers for the sync API."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.core.models import ConflictResolution, SyncAction, SyncConflict
from apps.core.sync.handlers import SyncOperationInput

# A batch is bounded: a device that has been offline for a week should flush in
# several requests rather than one that times out on a 2G link and gets retried
# from scratch.
MAX_BATCH_SIZE = 200


class SyncOperationSerializer(serializers.Serializer):
    client_op_id = serializers.UUIDField(
        help_text="Client-generated UUID. Replaying the same id is a no-op."
    )
    entity = serializers.CharField(max_length=100)
    action = serializers.ChoiceField(choices=SyncAction.choices)
    payload = serializers.JSONField(required=False, default=dict)
    client_timestamp = serializers.DateTimeField(
        required=False,
        allow_null=True,
        help_text="Device clock. Stored for ordering and disputes; the server's own clock is authoritative.",
    )
    device_id = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")

    def to_input(self) -> SyncOperationInput:
        data = self.validated_data
        return SyncOperationInput(
            client_op_id=str(data["client_op_id"]),
            entity=data["entity"],
            action=data["action"],
            payload=data.get("payload") or {},
            client_timestamp=data.get("client_timestamp"),
            device_id=data.get("device_id") or "",
        )


class SyncBatchSerializer(serializers.Serializer):
    operations = SyncOperationSerializer(many=True, allow_empty=False)

    def validate_operations(self, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(value) > MAX_BATCH_SIZE:
            raise serializers.ValidationError(
                f"A batch may carry at most {MAX_BATCH_SIZE} operations; split the queue."
            )
        seen: set[str] = set()
        for op in value:
            key = str(op["client_op_id"])
            if key in seen:
                raise serializers.ValidationError(
                    f"Duplicate client_op_id {key} within the same batch."
                )
            seen.add(key)
        return value

    def to_inputs(self) -> list[SyncOperationInput]:
        return [
            SyncOperationInput(
                client_op_id=str(op["client_op_id"]),
                entity=op["entity"],
                action=op["action"],
                payload=op.get("payload") or {},
                client_timestamp=op.get("client_timestamp"),
                device_id=op.get("device_id") or "",
            )
            for op in self.validated_data["operations"]
        ]


class SyncConflictSerializer(serializers.ModelSerializer):
    entity_label = serializers.CharField(source="entity", read_only=True)
    resolved_by_name = serializers.CharField(source="resolved_by.get_full_name", read_only=True)
    device_id = serializers.CharField(source="sync_operation.device_id", read_only=True)

    class Meta:
        model = SyncConflict
        fields = [
            "id",
            "entity",
            "entity_label",
            "field_name",
            "server_value",
            "client_value",
            "server_updated_at",
            "client_timestamp",
            "status",
            "resolution_reason",
            "resolved_by_name",
            "resolved_at",
            "device_id",
            "created_at",
        ]
        read_only_fields = fields


class ConflictResolutionSerializer(serializers.Serializer):
    resolution = serializers.ChoiceField(
        choices=[
            ConflictResolution.RESOLVED_SERVER,
            ConflictResolution.RESOLVED_CLIENT,
            ConflictResolution.DISMISSED,
        ]
    )
    # Mandatory: a resolved grade conflict without a stated reason is exactly the
    # gap FR-RPT-04 exists to close.
    reason = serializers.CharField(min_length=5, max_length=2000)
