from __future__ import annotations

from rest_framework import serializers

from apps.academics.models import (
    AcademicYear,
    GradeBand,
    GradingScale,
    Institution,
    Semester,
)
from apps.core.mixins import ModelCleanSerializerMixin


class InstitutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Institution
        fields = [
            "id",
            "name",
            "short_name",
            "mohest_code",
            "default_currency",
            "secondary_currency",
            "address",
            "phone",
            "email",
            "website",
            "attendance_threshold_percent",
            "timezone",
        ]


class SemesterSerializer(serializers.ModelSerializer):
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)
    registration_open = serializers.SerializerMethodField()

    class Meta:
        model = Semester
        fields = [
            "id",
            "academic_year",
            "academic_year_name",
            "sequence",
            "name",
            "teaching_start",
            "teaching_end",
            "exam_start",
            "exam_end",
            "registration_opens",
            "registration_closes",
            "add_drop_closes",
            "is_current",
            "registration_open",
        ]

    def get_registration_open(self, obj: Semester) -> bool:
        from apps.academics.services import calendar

        return calendar.is_registration_open(obj)


class AcademicYearSerializer(serializers.ModelSerializer):
    semesters = SemesterSerializer(many=True, read_only=True)

    class Meta:
        model = AcademicYear
        fields = ["id", "name", "start_date", "end_date", "is_current", "semesters"]


class GradeBandSerializer(ModelCleanSerializerMixin, serializers.ModelSerializer):
    """Nested read-only inside `GradingScaleSerializer`, and served writably by
    `GradeBandViewSet`. Per-row rules (`min <= max`, and the refusal to touch a
    band belonging to a locked scale) live in `GradeBand.clean()`, which the
    mixin runs so the API cannot bypass what the admin enforces."""

    class Meta:
        model = GradeBand
        fields = [
            "id",
            "scale",
            "letter",
            "min_percent",
            "max_percent",
            "grade_point",
            "is_pass",
            "description",
        ]


class GradingScaleSerializer(serializers.ModelSerializer):
    bands = GradeBandSerializer(many=True, read_only=True)

    class Meta:
        model = GradingScale
        fields = [
            "id",
            "name",
            "description",
            "max_grade_point",
            "pass_grade_point",
            "is_default",
            "is_locked",
            "effective_from",
            "bands",
        ]
