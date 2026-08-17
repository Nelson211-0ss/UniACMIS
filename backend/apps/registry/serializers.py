from __future__ import annotations

from rest_framework import serializers

from apps.registry.models import (
    NextOfKin,
    Sponsor,
    StaffProfile,
    Student,
    StudentDocument,
    StudentStatusHistory,
)


class NextOfKinSerializer(serializers.ModelSerializer):
    class Meta:
        model = NextOfKin
        fields = [
            "id",
            "full_name",
            "relationship",
            "phone",
            "alternate_phone",
            "email",
            "address",
            "is_primary",
        ]


class StudentDocumentSerializer(serializers.ModelSerializer):
    is_verified = serializers.BooleanField(read_only=True)

    class Meta:
        model = StudentDocument
        fields = [
            "id",
            "document_type",
            "title",
            "file",
            "file_size",
            "content_hash",
            "is_verified",
            "verified_at",
            "notes",
            "created_at",
        ]
        read_only_fields = ["file_size", "content_hash", "is_verified", "verified_at", "created_at"]


class StudentStatusHistorySerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(source="changed_by.get_full_name", read_only=True)

    class Meta:
        model = StudentStatusHistory
        fields = [
            "id",
            "from_status",
            "to_status",
            "reason",
            "effective_date",
            "reference",
            "changed_by_name",
            "created_at",
        ]
        read_only_fields = fields


class StudentListSerializer(serializers.ModelSerializer):
    """Deliberately lean: list views run over slow links, so they carry what a
    list needs and nothing more."""

    full_name = serializers.CharField(source="get_full_name", read_only=True)
    programme_code = serializers.CharField(source="programme.code", read_only=True)

    class Meta:
        model = Student
        fields = [
            "id",
            "student_id",
            "full_name",
            "programme",
            "programme_code",
            "current_level",
            "status",
            "gender",
        ]
        read_only_fields = fields


class StudentSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="get_full_name", read_only=True)
    programme_code = serializers.CharField(source="programme.code", read_only=True)
    programme_name = serializers.CharField(source="programme.name", read_only=True)
    entry_year_name = serializers.CharField(source="entry_academic_year.name", read_only=True)
    next_of_kin = NextOfKinSerializer(many=True, read_only=True)
    documents = StudentDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = Student
        fields = [
            "id",
            "student_id",
            "user",
            "full_name",
            "first_name",
            "middle_name",
            "last_name",
            "programme",
            "programme_code",
            "programme_name",
            "curriculum_version",
            "entry_academic_year",
            "entry_year_name",
            "current_level",
            "status",
            "sponsorship_type",
            "sponsor",
            "date_of_birth",
            "gender",
            "national_id_number",
            "passport_number",
            "nationality",
            "state_of_origin",
            "county",
            "has_disability",
            "disability_details",
            "phone",
            "alternate_phone",
            "email",
            "physical_address",
            "photo",
            "previous_institution",
            "previous_qualification",
            "transfer_credits",
            "admitted_on",
            "graduated_on",
            "next_of_kin",
            "documents",
            "created_at",
        ]
        read_only_fields = [
            "student_id",  # generated, never client-supplied
            "status",  # changed only through the status endpoint, which demands a reason
            "graduated_on",
            "created_at",
        ]


class StudentCreateSerializer(serializers.ModelSerializer):
    """Creation goes through `services.create_student`, which allocates the ID and
    opens the status history."""

    class Meta:
        model = Student
        fields = [
            "programme",
            "curriculum_version",
            "entry_academic_year",
            "first_name",
            "middle_name",
            "last_name",
            "date_of_birth",
            "gender",
            "national_id_number",
            "passport_number",
            "nationality",
            "state_of_origin",
            "county",
            "has_disability",
            "disability_details",
            "phone",
            "alternate_phone",
            "email",
            "physical_address",
            "sponsorship_type",
            "sponsor",
            "current_level",
            "previous_institution",
            "previous_qualification",
            "transfer_credits",
            "admitted_on",
        ]


class StatusChangeSerializer(serializers.Serializer):
    status = serializers.CharField()
    reason = serializers.CharField(min_length=5, max_length=2000)
    effective_date = serializers.DateField(required=False, allow_null=True)
    reference = serializers.CharField(required=False, allow_blank=True, max_length=100)


class SponsorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sponsor
        fields = [
            "id",
            "name",
            "sponsor_type",
            "contact_person",
            "phone",
            "email",
            "address",
            "notes",
            "is_active",
        ]


class StaffProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="get_full_name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    department_code = serializers.CharField(source="department.code", read_only=True)

    class Meta:
        model = StaffProfile
        fields = [
            "id",
            "staff_number",
            "user",
            "full_name",
            "email",
            "department",
            "department_code",
            "staff_category",
            "appointment_type",
            "rank",
            "highest_qualification",
            "date_of_hire",
            "contract_end_date",
            "phone",
            "gender",
            "is_active",
        ]
