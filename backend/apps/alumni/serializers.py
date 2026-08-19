from __future__ import annotations

from rest_framework import serializers

from apps.alumni.models import AlumniEvent, AlumniProfile


class AlumniProfileSerializer(serializers.ModelSerializer):
    student_number = serializers.CharField(source="student.student_id", read_only=True)
    student_name = serializers.CharField(source="student.get_full_name", read_only=True)

    class Meta:
        model = AlumniProfile
        fields = [
            "id",
            "student",
            "student_number",
            "student_name",
            "phone",
            "email",
            "current_employer",
            "current_position",
            "employment_status",
            "is_contactable",
            "notes",
        ]


class AlumniEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlumniEvent
        fields = ["id", "title", "description", "event_date", "location"]
