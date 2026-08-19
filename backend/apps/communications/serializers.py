from __future__ import annotations

from rest_framework import serializers

from apps.communications.models import Announcement


class AnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = [
            "id",
            "title",
            "body",
            "audience_type",
            "programme",
            "sent_at",
            "recipient_count",
            "sms_sent_count",
            "email_sent_count",
        ]
        read_only_fields = ["sent_at", "recipient_count", "sms_sent_count", "email_sent_count"]


class SendAnnouncementSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    body = serializers.CharField(max_length=5000)
    audience_type = serializers.ChoiceField(choices=["all_students", "programme", "alumni"])
    programme = serializers.IntegerField(required=False, allow_null=True)
