from __future__ import annotations

from django.contrib import admin

from apps.communications.models import Announcement


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ["title", "audience_type", "programme", "sent_at", "recipient_count"]
    list_filter = ["audience_type", "sent_at"]
    search_fields = ["title", "body"]
    autocomplete_fields = ["programme", "created_by"]
    readonly_fields = ["sent_at", "recipient_count", "sms_sent_count", "email_sent_count"]
