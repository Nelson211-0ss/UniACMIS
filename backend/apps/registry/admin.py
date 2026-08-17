"""Registry admin — the registrar's working interface through Phase 1."""

from __future__ import annotations

from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _

from apps.registry.models import (
    NextOfKin,
    Sponsor,
    StaffProfile,
    Student,
    StudentDocument,
    StudentStatus,
    StudentStatusHistory,
)


class NextOfKinInline(admin.TabularInline):
    model = NextOfKin
    extra = 0
    fields = ["full_name", "relationship", "phone", "alternate_phone", "email", "is_primary"]


class StudentDocumentInline(admin.TabularInline):
    model = StudentDocument
    extra = 0
    fields = ["document_type", "title", "file", "verified_by", "verified_at"]
    readonly_fields = ["verified_by", "verified_at"]


class StudentStatusHistoryInline(admin.TabularInline):
    model = StudentStatusHistory
    extra = 0
    fields = ["effective_date", "from_status", "to_status", "reason", "reference", "changed_by"]
    readonly_fields = fields
    ordering = ["-effective_date"]
    can_delete = False

    def has_add_permission(self, request, obj=None) -> bool:
        # Status changes are made on the student record so the transition rules and
        # the audit entry both apply; a hand-written history row would bypass both.
        return False


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = [
        "student_id",
        "get_full_name",
        "programme",
        "current_level",
        "status",
        "sponsorship_type",
        "gender",
        "state_of_origin",
    ]
    list_filter = [
        "status",
        "current_level",
        "sponsorship_type",
        "gender",
        "has_disability",
        "state_of_origin",
        "programme__department__faculty",
        "programme",
        "entry_academic_year",
    ]
    search_fields = [
        "student_id",
        "first_name",
        "middle_name",
        "last_name",
        "national_id_number",
        "phone",
        "email",
    ]
    autocomplete_fields = [
        "programme",
        "curriculum_version",
        "entry_academic_year",
        "sponsor",
        "user",
    ]
    readonly_fields = ["student_id", "created_at", "updated_at"]
    inlines = [NextOfKinInline, StudentDocumentInline, StudentStatusHistoryInline]
    date_hierarchy = "admitted_on"
    list_select_related = ["programme", "entry_academic_year"]

    fieldsets = (
        (
            _("Identity"),
            {
                "fields": ("student_id", "user", "photo"),
                "description": _(
                    "The student ID is generated from the institution's template and "
                    "is never reused. The portal login can be attached later."
                ),
            },
        ),
        (
            _("Academic placement"),
            {
                "fields": (
                    "programme",
                    "curriculum_version",
                    "entry_academic_year",
                    "current_level",
                    "status",
                    "admitted_on",
                    "graduated_on",
                )
            },
        ),
        (_("Sponsorship"), {"fields": ("sponsorship_type", "sponsor")}),
        (
            _("Personal details"),
            {
                "fields": (
                    "first_name",
                    "middle_name",
                    "last_name",
                    "date_of_birth",
                    "gender",
                    "nationality",
                    "national_id_number",
                    "passport_number",
                )
            },
        ),
        (
            _("Origin and needs"),
            {
                "fields": ("state_of_origin", "county", "has_disability", "disability_details"),
                "description": _(
                    "Used for statutory returns disaggregated by state and disability."
                ),
            },
        ),
        (_("Contact"), {"fields": ("phone", "alternate_phone", "email", "physical_address")}),
        (
            _("Previous study"),
            {
                "fields": (
                    "previous_institution",
                    "previous_qualification",
                    "transfer_credits",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Record"),
            {"fields": ("is_active", "created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    @admin.display(description=_("name"), ordering="last_name")
    def get_full_name(self, obj: Student) -> str:
        return obj.get_full_name()

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj is not None and obj.status in {StudentStatus.GRADUATED, StudentStatus.EXPELLED}:
            # Terminal statuses: editing one here would skip the transition rules
            # and leave the status history disagreeing with the record.
            fields.append("status")
        return fields

    def save_model(self, request, obj, form, change) -> None:
        status_changed = change and "status" in form.changed_data

        if status_changed:
            from apps.registry import services

            previous = form.initial.get("status")
            try:
                services.change_status(
                    obj,
                    obj.status,
                    reason=_("Changed from the admin by %(user)s")
                    % {"user": request.user.get_full_name()},
                    actor=request.user,
                )
            except Exception as exc:
                obj.status = previous
                messages.error(request, str(exc))
            # change_status saved the record and opened the history entry.
            return

        obj.audit_reason = _("Edited in the admin")
        super().save_model(request, obj, form, change)


@admin.register(StudentStatusHistory)
class StudentStatusHistoryAdmin(admin.ModelAdmin):
    list_display = [
        "student",
        "effective_date",
        "from_status",
        "to_status",
        "changed_by",
        "reference",
    ]
    list_filter = ["to_status", "effective_date"]
    search_fields = ["student__student_id", "student__last_name", "reason", "reference"]
    autocomplete_fields = ["student"]
    readonly_fields = [f.name for f in StudentStatusHistory._meta.fields]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(StudentDocument)
class StudentDocumentAdmin(admin.ModelAdmin):
    list_display = ["student", "document_type", "title", "file_size", "is_verified", "created_at"]
    list_filter = ["document_type", "verified_at"]
    search_fields = ["student__student_id", "student__last_name", "title", "content_hash"]
    autocomplete_fields = ["student"]
    readonly_fields = ["file_size", "content_hash", "uploaded_by", "verified_by", "verified_at"]
    actions = ["mark_verified"]

    @admin.display(boolean=True, description=_("verified"))
    def is_verified(self, obj: StudentDocument) -> bool:
        return obj.is_verified

    @admin.action(description=_("Mark selected documents as verified"))
    def mark_verified(self, request, queryset) -> None:
        from apps.registry import services

        count = 0
        for document in queryset.filter(verified_at__isnull=True):
            services.verify_document(document, verified_by=request.user)
            count += 1
        self.message_user(request, _("%(n)d document(s) verified.") % {"n": count})


@admin.register(Sponsor)
class SponsorAdmin(admin.ModelAdmin):
    list_display = ["name", "sponsor_type", "contact_person", "phone", "student_count", "is_active"]
    list_filter = ["sponsor_type", "is_active"]
    search_fields = ["name", "contact_person", "email"]

    @admin.display(description=_("students"))
    def student_count(self, obj: Sponsor) -> int:
        return obj.students.count()


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = [
        "staff_number",
        "get_full_name",
        "department",
        "staff_category",
        "rank",
        "appointment_type",
        "is_active",
    ]
    list_filter = ["staff_category", "rank", "appointment_type", "is_active", "department"]
    search_fields = [
        "staff_number",
        "user__first_name",
        "user__last_name",
        "user__email",
        "national_id_number",
    ]
    autocomplete_fields = ["user", "department"]
    list_select_related = ["user", "department"]

    @admin.display(description=_("name"), ordering="user__last_name")
    def get_full_name(self, obj: StaffProfile) -> str:
        return obj.get_full_name()
