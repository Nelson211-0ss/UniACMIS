"""Timetabling admin — the registrar's working view for building both schedules."""

from __future__ import annotations

from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _

from apps.timetabling import services
from apps.timetabling.models import ExamTimetable, Room, TimetableEntry


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "building", "capacity", "is_active"]
    list_filter = ["is_active", "building"]
    search_fields = ["code", "name"]


@admin.register(TimetableEntry)
class TimetableEntryAdmin(admin.ModelAdmin):
    list_display = [
        "course",
        "semester",
        "day_of_week",
        "start_time",
        "end_time",
        "room",
        "lecturer",
        "is_published",
    ]
    list_filter = ["semester", "day_of_week", "is_published", "course__department__faculty"]
    search_fields = ["course__code", "course__title"]
    autocomplete_fields = ["course", "semester", "room", "lecturer"]
    readonly_fields = ["is_published", "published_at", "published_by"]
    actions = ["publish_selected"]

    def save_model(self, request, obj, form, change) -> None:
        obj.audit_reason = _("Edited in the admin")
        super().save_model(request, obj, form, change)

    @admin.action(description=_("Publish the timetable for this semester"))
    def publish_selected(self, request, queryset) -> None:
        semester_ids = set(queryset.values_list("semester_id", flat=True))
        total = 0
        for semester_id in semester_ids:
            total += services.publish_timetable(semester_id, request.user)
        messages.success(request, _("%(n)d entrie(s) published.") % {"n": total})


@admin.register(ExamTimetable)
class ExamTimetableAdmin(admin.ModelAdmin):
    list_display = [
        "course",
        "semester",
        "exam_date",
        "start_time",
        "end_time",
        "room",
        "is_published",
    ]
    list_filter = ["semester", "exam_date", "is_published"]
    search_fields = ["course__code", "course__title"]
    autocomplete_fields = ["course", "semester", "room"]
    filter_horizontal = ["invigilators"]
    readonly_fields = ["is_published", "published_at", "published_by"]
    actions = ["publish_selected"]

    def save_model(self, request, obj, form, change) -> None:
        obj.audit_reason = _("Edited in the admin")
        super().save_model(request, obj, form, change)

    @admin.action(description=_("Publish the exam timetable for this semester"))
    def publish_selected(self, request, queryset) -> None:
        semester_ids = set(queryset.values_list("semester_id", flat=True))
        total = 0
        for semester_id in semester_ids:
            total += services.publish_exam_timetable(semester_id, request.user)
        messages.success(request, _("%(n)d entrie(s) published.") % {"n": total})
