from __future__ import annotations

from rest_framework import serializers

from apps.core.mixins import ModelCleanSerializerMixin
from apps.curriculum.models import (
    Course,
    CurriculumCourse,
    CurriculumVersion,
    Department,
    Faculty,
    Prerequisite,
    Programme,
)


class FacultySerializer(serializers.ModelSerializer):
    department_count = serializers.IntegerField(source="departments.count", read_only=True)

    class Meta:
        model = Faculty
        fields = ["id", "code", "name", "description", "dean", "is_active", "department_count"]


class DepartmentSerializer(serializers.ModelSerializer):
    faculty_code = serializers.CharField(source="faculty.code", read_only=True)

    class Meta:
        model = Department
        fields = [
            "id",
            "code",
            "name",
            "description",
            "faculty",
            "faculty_code",
            "head",
            "is_active",
        ]


class ProgrammeSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    faculty_code = serializers.CharField(source="department.faculty.code", read_only=True)

    class Meta:
        model = Programme
        fields = [
            "id",
            "code",
            "name",
            "award",
            "department",
            "department_name",
            "faculty_code",
            "duration_years",
            "total_credits_required",
            "min_credits_per_semester",
            "max_credits_per_semester",
            "entry_requirements",
            "description",
            "is_active",
        ]


class PrerequisiteSerializer(ModelCleanSerializerMixin, serializers.ModelSerializer):
    required_course_code = serializers.CharField(source="required_course.code", read_only=True)

    class Meta:
        model = Prerequisite
        fields = [
            "id",
            "course",
            "required_course",
            "required_course_code",
            "minimum_grade_point",
            "is_concurrent_allowed",
        ]


class CourseSerializer(serializers.ModelSerializer):
    department_code = serializers.CharField(source="department.code", read_only=True)
    prerequisites = PrerequisiteSerializer(many=True, read_only=True)

    class Meta:
        model = Course
        fields = [
            "id",
            "code",
            "title",
            "description",
            "department",
            "department_code",
            "credit_hours",
            "level",
            "contact_hours_per_week",
            "is_active",
            "prerequisites",
        ]


class CurriculumCourseSerializer(ModelCleanSerializerMixin, serializers.ModelSerializer):
    course_code = serializers.CharField(source="course.code", read_only=True)
    course_title = serializers.CharField(source="course.title", read_only=True)
    credit_hours = serializers.IntegerField(source="course.credit_hours", read_only=True)

    class Meta:
        model = CurriculumCourse
        fields = [
            "id",
            # Writable so a row can be attached through `CurriculumCourseViewSet`;
            # redundant but harmless in the read-only nested use under
            # `CurriculumVersionSerializer.courses`, where it is the parent's id.
            "curriculum_version",
            "course",
            "course_code",
            "course_title",
            "credit_hours",
            "year_of_study",
            "semester_sequence",
            "is_core",
            "elective_group",
            "min_group_choices",
        ]


class CurriculumVersionSerializer(serializers.ModelSerializer):
    programme_code = serializers.CharField(source="programme.code", read_only=True)
    courses = CurriculumCourseSerializer(many=True, read_only=True)
    core_credits = serializers.IntegerField(source="total_core_credits", read_only=True)

    class Meta:
        model = CurriculumVersion
        fields = [
            "id",
            "programme",
            "programme_code",
            "version",
            "status",
            "effective_from",
            "effective_to",
            "notes",
            "core_credits",
            "courses",
        ]
