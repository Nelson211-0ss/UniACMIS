from __future__ import annotations

from django.contrib import admin

from apps.hostel.models import Allocation, HostelPolicy, Room


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ["building", "room_number", "capacity", "gender_restriction", "is_active"]
    list_filter = ["building", "gender_restriction", "is_active"]
    search_fields = ["building", "room_number"]

    def save_model(self, request, obj, form, change) -> None:
        obj.audit_reason = "Edited in the admin"
        super().save_model(request, obj, form, change)


@admin.register(Allocation)
class AllocationAdmin(admin.ModelAdmin):
    list_display = ["student", "room", "academic_year", "status", "allocated_at"]
    list_filter = ["academic_year", "status"]
    search_fields = ["student__student_id", "room__building", "room__room_number"]
    autocomplete_fields = ["student", "room", "academic_year", "allocated_by", "vacated_by"]
    readonly_fields = ["status", "allocated_at", "vacated_at"]


@admin.register(HostelPolicy)
class HostelPolicyAdmin(admin.ModelAdmin):
    list_display = ["termly_fee", "currency"]
