"""Finance admin — fee structures and scholarships are edited here directly;
invoices and payments are inspected here but created through the API/services
so the audit trail and receipt numbering stay consistent."""

from __future__ import annotations

from django.contrib import admin

from apps.finance.models import FeeStructure, Invoice, Payment, Refund, Scholarship


@admin.register(FeeStructure)
class FeeStructureAdmin(admin.ModelAdmin):
    list_display = [
        "programme",
        "academic_year",
        "level",
        "residency",
        "amount",
        "currency",
        "is_active",
    ]
    list_filter = ["academic_year", "level", "residency", "is_active"]
    search_fields = ["programme__code", "programme__name"]
    autocomplete_fields = ["programme", "academic_year"]

    def save_model(self, request, obj, form, change) -> None:
        obj.audit_reason = "Edited in the admin"
        super().save_model(request, obj, form, change)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ["invoice_number", "student", "semester", "amount", "status", "due_date"]
    list_filter = ["status", "semester"]
    search_fields = ["invoice_number", "student__student_id", "student__last_name"]
    autocomplete_fields = ["student", "semester", "fee_structure", "issued_by"]
    readonly_fields = ["invoice_number", "status"]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["reference", "invoice", "method", "amount", "status", "receipt_number"]
    list_filter = ["method", "status"]
    search_fields = ["reference", "receipt_number", "invoice__invoice_number"]
    autocomplete_fields = ["invoice", "received_by"]
    readonly_fields = ["status", "receipt_number", "confirmed_at"]


@admin.register(Scholarship)
class ScholarshipAdmin(admin.ModelAdmin):
    list_display = ["student", "sponsor", "academic_year", "coverage_type", "is_active"]
    list_filter = ["academic_year", "coverage_type", "is_active"]
    autocomplete_fields = ["student", "sponsor", "academic_year"]

    def save_model(self, request, obj, form, change) -> None:
        obj.audit_reason = "Edited in the admin"
        super().save_model(request, obj, form, change)


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ["payment", "amount", "status", "decided_by", "decided_at"]
    list_filter = ["status"]
    autocomplete_fields = ["payment", "requested_by", "decided_by"]
    readonly_fields = ["status", "decided_at", "paid_at"]
