from __future__ import annotations

from django.contrib import admin

from apps.hr.models import Appraisal, Contract, LeaveRequest


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ["staff", "position", "contract_type", "start_date", "end_date", "is_active"]
    list_filter = ["contract_type", "is_active"]
    search_fields = ["staff__staff_number", "position"]
    autocomplete_fields = ["staff"]

    def save_model(self, request, obj, form, change) -> None:
        obj.audit_reason = "Edited in the admin"
        super().save_model(request, obj, form, change)


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ["staff", "leave_type", "start_date", "end_date", "status"]
    list_filter = ["leave_type", "status"]
    search_fields = ["staff__staff_number"]
    autocomplete_fields = ["staff", "endorsed_by", "decided_by"]
    readonly_fields = ["status", "endorsed_at", "decided_at"]


@admin.register(Appraisal)
class AppraisalAdmin(admin.ModelAdmin):
    list_display = ["staff", "academic_year", "rating", "promotion_recommended"]
    list_filter = ["academic_year", "promotion_recommended"]
    search_fields = ["staff__staff_number"]
    autocomplete_fields = ["staff", "academic_year", "reviewer"]

    def save_model(self, request, obj, form, change) -> None:
        obj.audit_reason = "Edited in the admin"
        super().save_model(request, obj, form, change)
