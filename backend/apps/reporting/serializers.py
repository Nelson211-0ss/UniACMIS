from __future__ import annotations

from rest_framework import serializers

from apps.reporting.models import DashboardWidget


class DashboardWidgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = DashboardWidget
        fields = ["id", "key", "label", "is_enabled", "sort_order"]


class PassRateQuerySerializer(serializers.Serializer):
    course = serializers.IntegerField()
    semester = serializers.IntegerField()
