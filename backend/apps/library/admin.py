from __future__ import annotations

from django.contrib import admin

from apps.library.models import LibraryItem, LibraryPolicy, Loan


@admin.register(LibraryItem)
class LibraryItemAdmin(admin.ModelAdmin):
    list_display = ["title", "author", "item_type", "is_electronic", "total_copies", "is_active"]
    list_filter = ["item_type", "is_electronic", "is_active"]
    search_fields = ["title", "author", "isbn"]

    def save_model(self, request, obj, form, change) -> None:
        obj.audit_reason = "Edited in the admin"
        super().save_model(request, obj, form, change)


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = [
        "item",
        "borrower_student",
        "borrower_staff",
        "due_date",
        "status",
        "fine_amount",
    ]
    list_filter = ["status", "fine_waived"]
    search_fields = ["item__title", "borrower_student__student_id", "borrower_staff__staff_number"]
    autocomplete_fields = ["item", "borrower_student", "borrower_staff", "waived_by"]
    readonly_fields = ["status", "returned_at", "fine_amount"]


@admin.register(LibraryPolicy)
class LibraryPolicyAdmin(admin.ModelAdmin):
    list_display = ["loan_period_days", "daily_fine_rate", "currency"]
