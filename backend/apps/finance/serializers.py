from __future__ import annotations

from rest_framework import serializers

from apps.finance import services
from apps.finance.models import (
    FeeStructure,
    Invoice,
    Payment,
    PaymentMethod,
    Refund,
    Scholarship,
)


class FeeStructureSerializer(serializers.ModelSerializer):
    programme_code = serializers.CharField(source="programme.code", read_only=True)
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)

    class Meta:
        model = FeeStructure
        fields = [
            "id",
            "programme",
            "programme_code",
            "academic_year",
            "academic_year_name",
            "level",
            "residency",
            "amount",
            "currency",
            "is_active",
        ]


class InvoiceSerializer(serializers.ModelSerializer):
    student_number = serializers.CharField(source="student.student_id", read_only=True)
    student_name = serializers.CharField(source="student.get_full_name", read_only=True)
    semester_display = serializers.CharField(source="semester.__str__", read_only=True)
    net_amount = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    balance = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            "id",
            "invoice_number",
            "student",
            "student_number",
            "student_name",
            "semester",
            "semester_display",
            "amount",
            "discount_amount",
            "net_amount",
            "balance",
            "currency",
            "status",
            "due_date",
            "created_at",
        ]
        read_only_fields = fields

    def get_balance(self, obj: Invoice) -> str:
        return str(services.invoice_balance(obj))


class GenerateInvoiceSerializer(serializers.Serializer):
    student = serializers.IntegerField()
    semester = serializers.IntegerField()
    due_date = serializers.DateField(required=False, allow_null=True)


class GenerateInvoicesForSemesterSerializer(serializers.Serializer):
    semester = serializers.IntegerField()


class PaymentSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="invoice.invoice_number", read_only=True)
    student_number = serializers.CharField(source="invoice.student.student_id", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "invoice",
            "invoice_number",
            "student_number",
            "method",
            "amount",
            "currency",
            "provider",
            "reference",
            "status",
            "receipt_number",
            "confirmed_at",
            "notes",
            "created_at",
        ]
        read_only_fields = fields


class RecordManualPaymentSerializer(serializers.Serializer):
    invoice = serializers.IntegerField()
    method = serializers.ChoiceField(
        choices=[PaymentMethod.CASH, PaymentMethod.CHEQUE, PaymentMethod.BANK_SLIP]
    )
    amount = serializers.DecimalField(max_digits=16, decimal_places=2)
    reference = serializers.CharField(max_length=120)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class RejectPaymentSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=5, max_length=2000)


class InitiateMobilePaymentSerializer(serializers.Serializer):
    invoice = serializers.IntegerField()
    payer_ref = serializers.CharField(max_length=100)
    amount = serializers.DecimalField(
        max_digits=16, decimal_places=2, required=False, allow_null=True
    )


class ScholarshipSerializer(serializers.ModelSerializer):
    student_number = serializers.CharField(source="student.student_id", read_only=True)
    sponsor_name = serializers.CharField(source="sponsor.name", read_only=True, default="")

    class Meta:
        model = Scholarship
        fields = [
            "id",
            "student",
            "student_number",
            "sponsor",
            "sponsor_name",
            "academic_year",
            "coverage_type",
            "percentage",
            "fixed_amount",
            "currency",
            "is_active",
            "notes",
        ]


class RefundSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="payment.invoice.invoice_number", read_only=True)

    class Meta:
        model = Refund
        fields = [
            "id",
            "payment",
            "invoice_number",
            "amount",
            "currency",
            "reason",
            "status",
            "decision_notes",
            "decided_at",
            "paid_at",
            "created_at",
        ]
        read_only_fields = [
            "status",
            "decision_notes",
            "decided_at",
            "paid_at",
            "created_at",
        ]


class RequestRefundSerializer(serializers.Serializer):
    payment = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=16, decimal_places=2)
    reason = serializers.CharField(min_length=5, max_length=2000)


class DecideRefundSerializer(serializers.Serializer):
    approve = serializers.BooleanField()
    notes = serializers.CharField(min_length=5, max_length=2000)


class DefaulterRowSerializer(serializers.Serializer):
    invoice_id = serializers.IntegerField()
    invoice_number = serializers.CharField()
    student_id = serializers.IntegerField()
    student_number = serializers.CharField()
    student_name = serializers.CharField()
    semester_id = serializers.IntegerField()
    balance = serializers.DecimalField(max_digits=16, decimal_places=2)
    currency = serializers.CharField()
    due_date = serializers.DateField()
    days_overdue = serializers.IntegerField()
