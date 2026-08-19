from __future__ import annotations

from rest_framework import serializers

from apps.examinations.models import Assessment, GradeAppeal, Mark, ResultApproval


class AssessmentSerializer(serializers.ModelSerializer):
    course_code = serializers.CharField(source="course.code", read_only=True)

    class Meta:
        model = Assessment
        fields = [
            "id",
            "course",
            "course_code",
            "name",
            "weight_percent",
            "max_score",
            "sequence",
            "grade_entry_deadline",
        ]


class MarkSerializer(serializers.ModelSerializer):
    student_id = serializers.CharField(source="registration.student.student_id", read_only=True)
    student_name = serializers.CharField(
        source="registration.student.get_full_name", read_only=True
    )
    assessment_name = serializers.CharField(source="assessment.name", read_only=True)
    effective_score = serializers.DecimalField(max_digits=6, decimal_places=2, read_only=True)

    class Meta:
        model = Mark
        fields = [
            "id",
            "registration",
            "student_id",
            "student_name",
            "assessment",
            "assessment_name",
            "score",
            "effective_score",
            "is_late",
            "moderated_score",
            "moderation_notes",
            "is_irregular",
            "irregularity_notes",
            "created_at",
        ]
        read_only_fields = [
            "is_late",
            "moderated_score",
            "moderation_notes",
            "is_irregular",
            "irregularity_notes",
            "created_at",
        ]


class RecordMarkSerializer(serializers.Serializer):
    registration = serializers.IntegerField()
    assessment = serializers.IntegerField()
    score = serializers.DecimalField(max_digits=6, decimal_places=2)


class ModerateMarkSerializer(serializers.Serializer):
    moderated_score = serializers.DecimalField(max_digits=6, decimal_places=2)
    notes = serializers.CharField(min_length=5, max_length=2000)


class IrregularitySerializer(serializers.Serializer):
    notes = serializers.CharField(min_length=5, max_length=2000)


class MissingMarkSerializer(serializers.Serializer):
    registration_id = serializers.IntegerField()
    assessment_id = serializers.IntegerField()
    assessment_name = serializers.CharField()


class CourseResultComponentSerializer(serializers.Serializer):
    assessment = serializers.CharField()
    weight_percent = serializers.DecimalField(max_digits=5, decimal_places=2)
    score = serializers.DecimalField(max_digits=6, decimal_places=2, allow_null=True)
    max_score = serializers.DecimalField(
        max_digits=6, decimal_places=2, required=False, allow_null=True
    )


class CourseResultSerializer(serializers.Serializer):
    registration_id = serializers.IntegerField()
    course_id = serializers.IntegerField(required=False)
    components = CourseResultComponentSerializer(many=True)
    complete = serializers.BooleanField()
    has_irregularity = serializers.BooleanField()
    configuration_error = serializers.CharField(allow_null=True)
    percent = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True)
    letter = serializers.CharField(allow_null=True)
    grade_point = serializers.DecimalField(max_digits=4, decimal_places=2, allow_null=True)
    is_pass = serializers.BooleanField(allow_null=True)


class StudentResultSerializer(serializers.Serializer):
    published = serializers.BooleanField()
    withheld = serializers.BooleanField()
    holds = serializers.ListField(child=serializers.DictField(), required=False)
    courses = CourseResultSerializer(many=True)
    gpa = serializers.DecimalField(max_digits=4, decimal_places=2, allow_null=True)


class GradeAppealSerializer(serializers.ModelSerializer):
    student_id = serializers.CharField(source="registration.student.student_id", read_only=True)

    class Meta:
        model = GradeAppeal
        fields = [
            "id",
            "registration",
            "student_id",
            "assessment",
            "reason",
            "status",
            "decision_notes",
            "decided_at",
            "created_at",
        ]
        read_only_fields = ["status", "decision_notes", "decided_at", "created_at"]


class SubmitAppealSerializer(serializers.Serializer):
    registration = serializers.IntegerField()
    assessment = serializers.IntegerField(required=False, allow_null=True)
    reason = serializers.CharField(min_length=5, max_length=2000)


class DecideAppealSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["upheld", "rejected"])
    notes = serializers.CharField(min_length=5, max_length=2000)


class ResultApprovalSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResultApproval
        fields = [
            "id",
            "semester",
            "programme",
            "status",
            "approved_by",
            "approved_at",
            "approval_notes",
            "published_by",
            "published_at",
            "created_at",
        ]
        read_only_fields = fields


class SubmitApprovalSerializer(serializers.Serializer):
    semester = serializers.IntegerField()
    programme = serializers.IntegerField(required=False, allow_null=True)


class DecisionNotesSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class RejectApprovalSerializer(serializers.Serializer):
    notes = serializers.CharField(min_length=5, max_length=2000)
