from __future__ import annotations

from rest_framework import serializers

from apps.library.models import LibraryItem, Loan


class LibraryItemSerializer(serializers.ModelSerializer):
    available_copies = serializers.IntegerField(read_only=True)

    class Meta:
        model = LibraryItem
        fields = [
            "id",
            "title",
            "author",
            "isbn",
            "item_type",
            "is_electronic",
            "resource_url",
            "total_copies",
            "available_copies",
            "is_active",
        ]


class LoanSerializer(serializers.ModelSerializer):
    item_title = serializers.CharField(source="item.title", read_only=True)
    borrower_number = serializers.SerializerMethodField()
    owed = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)

    class Meta:
        model = Loan
        fields = [
            "id",
            "item",
            "item_title",
            "borrower_student",
            "borrower_staff",
            "borrower_number",
            "due_date",
            "returned_at",
            "status",
            "fine_amount",
            "owed",
            "currency",
            "fine_waived",
            "waived_reason",
            "created_at",
        ]
        read_only_fields = [
            "returned_at",
            "status",
            "fine_amount",
            "fine_waived",
            "waived_reason",
            "created_at",
        ]

    def get_borrower_number(self, obj: Loan) -> str:
        if obj.borrower_student_id:
            return obj.borrower_student.student_id
        if obj.borrower_staff_id:
            return obj.borrower_staff.staff_number
        return ""


class CheckoutSerializer(serializers.Serializer):
    item = serializers.IntegerField()
    borrower_student = serializers.IntegerField(required=False, allow_null=True)
    borrower_staff = serializers.IntegerField(required=False, allow_null=True)
    due_date = serializers.DateField(required=False, allow_null=True)


class WaiveFineSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=5, max_length=2000)
