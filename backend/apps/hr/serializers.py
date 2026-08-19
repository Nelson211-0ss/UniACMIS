from __future__ import annotations

from rest_framework import serializers

from apps.hr.models import Appraisal, Contract, LeaveRequest


class ContractSerializer(serializers.ModelSerializer):
    staff_number = serializers.CharField(source="staff.staff_number", read_only=True)

    class Meta:
        model = Contract
        fields = [
            "id",
            "staff",
            "staff_number",
            "contract_type",
            "position",
            "start_date",
            "end_date",
            "basic_salary",
            "currency",
            "is_active",
            "notes",
        ]


class EndContractSerializer(serializers.Serializer):
    end_date = serializers.DateField()


class LeaveRequestSerializer(serializers.ModelSerializer):
    staff_number = serializers.CharField(source="staff.staff_number", read_only=True)

    class Meta:
        model = LeaveRequest
        fields = [
            "id",
            "staff",
            "staff_number",
            "leave_type",
            "start_date",
            "end_date",
            "reason",
            "status",
            "endorsed_at",
            "decision_notes",
            "decided_at",
            "created_at",
        ]
        read_only_fields = ["status", "endorsed_at", "decision_notes", "decided_at", "created_at"]


class SubmitLeaveRequestSerializer(serializers.Serializer):
    staff = serializers.IntegerField()
    leave_type = serializers.ChoiceField(
        choices=["annual", "sick", "maternity", "paternity", "study", "unpaid"]
    )
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    reason = serializers.CharField(min_length=5, max_length=2000)


class DecideLeaveRequestSerializer(serializers.Serializer):
    approve = serializers.BooleanField()
    notes = serializers.CharField(min_length=5, max_length=2000)


class AppraisalSerializer(serializers.ModelSerializer):
    staff_number = serializers.CharField(source="staff.staff_number", read_only=True)

    class Meta:
        model = Appraisal
        fields = [
            "id",
            "staff",
            "staff_number",
            "academic_year",
            "reviewer",
            "rating",
            "comments",
            "promotion_recommended",
        ]
        read_only_fields = ["reviewer"]


class PayrollRowSerializer(serializers.Serializer):
    staff_id = serializers.IntegerField()
    staff_number = serializers.CharField()
    staff_name = serializers.CharField()
    position = serializers.CharField()
    contract_type = serializers.CharField()
    basic_salary = serializers.DecimalField(max_digits=16, decimal_places=2)
    currency = serializers.CharField()
