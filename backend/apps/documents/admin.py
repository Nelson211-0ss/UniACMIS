from __future__ import annotations

from django.contrib import admin

from apps.documents.models import IssuedDocument, TranscriptRequest


@admin.register(TranscriptRequest)
class TranscriptRequestAdmin(admin.ModelAdmin):
    list_display = ["student", "status", "decided_by", "decided_at"]
    list_filter = ["status"]
    search_fields = ["student__student_id", "student__last_name"]
    autocomplete_fields = ["student", "decided_by"]
    readonly_fields = ["status", "decided_at"]


@admin.register(IssuedDocument)
class IssuedDocumentAdmin(admin.ModelAdmin):
    list_display = ["serial_number", "student", "document_type", "issued_at", "is_revoked"]
    list_filter = ["document_type", "is_revoked"]
    search_fields = ["serial_number", "student__student_id"]
    autocomplete_fields = ["student", "transcript_request", "issued_by"]
    readonly_fields = ["serial_number", "issued_at", "is_revoked", "revoked_at"]
