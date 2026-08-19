from __future__ import annotations

from rest_framework import serializers

from apps.enrollment.models import CourseRegistration


class CourseRegistrationSerializer(serializers.ModelSerializer):
    student_display = serializers.CharField(source="student.get_full_name", read_only=True)
    student_number = serializers.CharField(source="student.student_id", read_only=True)
    course_code = serializers.CharField(source="course.code", read_only=True)
    course_title = serializers.CharField(source="course.title", read_only=True)
    credit_hours = serializers.IntegerField(source="course.credit_hours", read_only=True)
    semester_display = serializers.CharField(source="semester.__str__", read_only=True)

    class Meta:
        model = CourseRegistration
        fields = [
            "id",
            "student",
            "student_display",
            "student_number",
            "course",
            "course_code",
            "course_title",
            "credit_hours",
            "semester",
            "semester_display",
            "status",
            "is_repeat",
            "hold_override_by",
            "override_reason",
            "drop_reason",
            "dropped_at",
            "created_at",
        ]
        read_only_fields = [
            "status",
            "is_repeat",
            "hold_override_by",
            "dropped_at",
        ]


class RegisterCourseSerializer(serializers.ModelSerializer):
    """A `ModelSerializer` over `CourseRegistration`'s own FK fields, not a
    plain `Serializer` with bare integers — DRF builds `student`/`course`/
    `semester` into `PrimaryKeyRelatedField`s from the model's own (lazily
    referenced) foreign keys, which validates that each id actually exists
    with no import of `registry`/`curriculum`/`academics` models here at all.
    """

    override_reason = serializers.CharField(required=False, allow_blank=True, max_length=2000)

    class Meta:
        model = CourseRegistration
        fields = ["student", "course", "semester", "override_reason"]
        extra_kwargs = {"semester": {"required": False}}
        # DRF auto-attaches a UniqueTogetherValidator from the model's own
        # UniqueConstraint on (student, course, semester). That would reject a
        # legitimate re-register-after-drop before `register_course` ever runs
        # — it only knows "a row exists", not that the existing row is DROPPED
        # and this is meant to reactivate it. The service layer is the actual
        # authority on that distinction, so the serializer defers to it.
        validators = []


class DropCourseSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=5, max_length=2000)


class CompletionSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=5, max_length=2000)


class ClassListEntrySerializer(serializers.Serializer):
    registration_id = serializers.IntegerField()
    student_id = serializers.CharField()
    full_name = serializers.CharField()
    is_repeat = serializers.BooleanField()


class CreditSummarySerializer(serializers.Serializer):
    registered_credits = serializers.IntegerField()
    min_credits = serializers.IntegerField()
    max_credits = serializers.IntegerField()
    meets_minimum = serializers.BooleanField()
