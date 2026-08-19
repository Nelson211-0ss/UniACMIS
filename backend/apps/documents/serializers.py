from __future__ import annotations

from rest_framework import serializers

from apps.documents.models import IssuedDocument, TranscriptRequest


class TranscriptRequestSerializer(serializers.ModelSerializer):
    student_number = serializers.CharField(source="student.student_id", read_only=True)

    class Meta:
        model = TranscriptRequest
        fields = [
            "id",
            "student",
            "student_number",
            "reason",
            "status",
            "decision_notes",
            "decided_at",
            "created_at",
        ]
        read_only_fields = ["status", "decision_notes", "decided_at", "created_at"]


class RequestTranscriptSerializer(serializers.Serializer):
    student = serializers.IntegerField(
        required=False, help_text="Staff only — the student this request is filed on behalf of."
    )
    reason = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class DecideTranscriptRequestSerializer(serializers.Serializer):
    approve = serializers.BooleanField()
    notes = serializers.CharField(min_length=5, max_length=2000)


class IssueCertificateSerializer(serializers.Serializer):
    student = serializers.IntegerField()
    override_reason = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class RevokeDocumentSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=5, max_length=2000)


class IssuedDocumentSerializer(serializers.ModelSerializer):
    student_number = serializers.CharField(source="student.student_id", read_only=True)
    is_valid = serializers.BooleanField(read_only=True)

    class Meta:
        model = IssuedDocument
        fields = [
            "id",
            "student",
            "student_number",
            "document_type",
            "serial_number",
            "issued_at",
            "is_revoked",
            "is_valid",
        ]
        read_only_fields = ["serial_number", "issued_at", "is_revoked"]


class VerificationResultSerializer(serializers.Serializer):
    serial_number = serializers.CharField()
    document_type = serializers.CharField()
    student_name = serializers.CharField()
    issued_at = serializers.DateTimeField()
    is_valid = serializers.BooleanField()


class ClearanceStatusSerializer(serializers.Serializer):
    clear = serializers.BooleanField()
    holds = serializers.ListField(child=serializers.DictField())
