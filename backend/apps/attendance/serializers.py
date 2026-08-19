from __future__ import annotations

from rest_framework import serializers

from apps.attendance.models import AttendanceStatus, SessionRecord


class SessionRecordSerializer(serializers.ModelSerializer):
    student_id = serializers.CharField(source="registration.student.student_id", read_only=True)
    student_name = serializers.CharField(
        source="registration.student.get_full_name", read_only=True
    )
    course_code = serializers.CharField(source="timetable_entry.course.code", read_only=True)

    class Meta:
        model = SessionRecord
        fields = [
            "id",
            "timetable_entry",
            "registration",
            "student_id",
            "student_name",
            "course_code",
            "session_date",
            "status",
            "notes",
            "recorded_by",
            "created_at",
        ]
        read_only_fields = ["recorded_by", "created_at"]


class AttendanceMarkSerializer(serializers.Serializer):
    registration_id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=AttendanceStatus.choices)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=255)


class RecordSessionSerializer(serializers.Serializer):
    timetable_entry = serializers.IntegerField()
    session_date = serializers.DateField()
    marks = AttendanceMarkSerializer(many=True, allow_empty=False)


class AttendanceSummarySerializer(serializers.Serializer):
    sessions_recorded = serializers.IntegerField()
    sessions_attended = serializers.IntegerField()
    percentage = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True)


class ExamEligibilitySerializer(AttendanceSummarySerializer):
    threshold = serializers.DecimalField(max_digits=5, decimal_places=2)
    below_threshold = serializers.BooleanField()
    waived = serializers.BooleanField()
    eligible = serializers.BooleanField()


class GrantWaiverSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=5, max_length=2000)
