from __future__ import annotations

from rest_framework import serializers

from apps.admissions.models import (
    Application,
    ApplicationDocument,
    ApplicationFeePayment,
    ApplicationReview,
)


class ApplicationDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplicationDocument
        fields = [
            "id",
            "document_type",
            "title",
            "file",
            "file_size",
            "content_hash",
            "verified_at",
            "created_at",
        ]
        read_only_fields = ["file_size", "content_hash", "verified_at", "created_at"]


class ApplicationReviewSerializer(serializers.ModelSerializer):
    reviewer_name = serializers.CharField(source="reviewer.get_full_name", read_only=True)

    class Meta:
        model = ApplicationReview
        fields = ["id", "reviewer_name", "score", "criteria", "comments", "created_at"]
        read_only_fields = fields


class ApplicationFeePaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplicationFeePayment
        fields = [
            "id",
            "provider",
            "reference",
            "amount",
            "currency",
            "status",
            "confirmed_at",
            "created_at",
        ]
        read_only_fields = fields


class ApplicationListSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="get_full_name", read_only=True)
    programme_code = serializers.CharField(source="programme.code", read_only=True)

    class Meta:
        model = Application
        fields = [
            "id",
            "reference_number",
            "full_name",
            "programme",
            "programme_code",
            "status",
            "score",
            "fee_paid",
            "created_at",
        ]
        read_only_fields = fields


class ApplicationSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="get_full_name", read_only=True)
    programme_code = serializers.CharField(source="programme.code", read_only=True)
    documents = ApplicationDocumentSerializer(many=True, read_only=True)
    reviews = ApplicationReviewSerializer(many=True, read_only=True)
    fee_payments = ApplicationFeePaymentSerializer(many=True, read_only=True)

    class Meta:
        model = Application
        fields = [
            "id",
            "reference_number",
            "full_name",
            "programme",
            "programme_code",
            "intended_academic_year",
            "first_name",
            "middle_name",
            "last_name",
            "date_of_birth",
            "gender",
            "nationality",
            "phone",
            "email",
            "national_id_number",
            "state_of_origin",
            "county",
            "has_disability",
            "disability_details",
            "physical_address",
            "previous_institution",
            "previous_qualification",
            "previous_grade",
            "status",
            "source",
            "submitted_at",
            "score",
            "decision_reason",
            "fee_paid",
            "student",
            "documents",
            "reviews",
            "fee_payments",
            "created_at",
        ]
        read_only_fields = [
            "reference_number",
            "status",
            "source",
            "submitted_at",
            "score",
            "decision_reason",
            "fee_paid",
            "student",
        ]


class ApplicationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Application
        fields = [
            "programme",
            "intended_academic_year",
            "first_name",
            "middle_name",
            "last_name",
            "date_of_birth",
            "gender",
            "nationality",
            "phone",
            "email",
            "national_id_number",
            "state_of_origin",
            "county",
            "has_disability",
            "disability_details",
            "physical_address",
            "previous_institution",
            "previous_qualification",
            "previous_grade",
        ]


class DecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["offered", "rejected"])
    reason = serializers.CharField(min_length=5, max_length=2000)


class ReviewSubmitSerializer(serializers.Serializer):
    score = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0)
    criteria = serializers.JSONField(required=False, default=dict)
    comments = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class WithdrawSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=5, max_length=2000)


class MeritListEntrySerializer(serializers.Serializer):
    application_id = serializers.IntegerField()
    reference_number = serializers.CharField()
    full_name = serializers.CharField()
    rank = serializers.IntegerField()
    score = serializers.DecimalField(max_digits=6, decimal_places=2, allow_null=True)
    admitted = serializers.BooleanField()
    quota_category = serializers.CharField(allow_null=True)
