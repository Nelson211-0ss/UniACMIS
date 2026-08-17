"""Admin for accounts. This is ICT's working interface in Phase 1."""

from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import Role, User, UserRole


class UserCreateForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email", "first_name", "middle_name", "last_name", "phone")


class UserEditForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"


class UserRoleInline(admin.TabularInline):
    model = UserRole
    fk_name = "user"
    extra = 0
    fields = ["role", "granted_by", "granted_at", "revoked_at", "reason"]
    readonly_fields = ["granted_by", "granted_at"]
    autocomplete_fields = ["role"]
    verbose_name = _("role assignment")
    verbose_name_plural = _("role assignments")


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    add_form = UserCreateForm
    form = UserEditForm
    model = User

    list_display = [
        "email",
        "get_full_name",
        "roles_display",
        "is_active",
        "mfa_enabled",
        "must_change_password",
        "last_login",
    ]
    list_filter = ["is_active", "is_staff", "is_superuser", "mfa_enabled", "role_assignments__role"]
    search_fields = ["email", "first_name", "middle_name", "last_name", "phone"]
    ordering = ["last_name", "first_name"]
    inlines = [UserRoleInline]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Name"), {"fields": ("first_name", "middle_name", "last_name")}),
        (_("Contact"), {"fields": ("phone",)}),
        (
            _("Access"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "mfa_enabled",
                    "must_change_password",
                    "groups",
                    "user_permissions",
                ),
                "description": _(
                    "Permissions come from roles. Assign a role below rather than "
                    "editing groups or individual permissions directly — a "
                    "hand-edited permission is invisible to the policy in roles.py."
                ),
            },
        ),
        (
            _("Sign-in history"),
            {
                "fields": ("last_login", "last_login_ip", "failed_login_attempts", "locked_until"),
            },
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "first_name",
                    "middle_name",
                    "last_name",
                    "phone",
                    "password1",
                    "password2",
                ),
            },
        ),
    )

    readonly_fields = ["last_login", "last_login_ip"]
    actions = ["unlock_accounts", "require_password_change"]

    @admin.display(description=_("roles"))
    def roles_display(self, obj: User) -> str:
        return ", ".join(obj.role_codes()) or "—"

    @admin.action(description=_("Unlock selected accounts"))
    def unlock_accounts(self, request, queryset) -> None:
        updated = queryset.update(locked_until=None, failed_login_attempts=0)
        self.message_user(request, _("%(n)d account(s) unlocked.") % {"n": updated})

    @admin.action(description=_("Require a password change at next sign-in"))
    def require_password_change(self, request, queryset) -> None:
        updated = queryset.update(must_change_password=True)
        self.message_user(request, _("%(n)d account(s) flagged.") % {"n": updated})


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "permission_count", "user_count", "is_system"]
    search_fields = ["code", "name", "description"]
    readonly_fields = ["code", "is_system", "group"]

    @admin.display(description=_("permissions"))
    def permission_count(self, obj: Role) -> int:
        return obj.group.permissions.count() if obj.group_id else 0

    @admin.display(description=_("users"))
    def user_count(self, obj: Role) -> int:
        return obj.user_assignments.filter(revoked_at__isnull=True).count()

    def has_add_permission(self, request) -> bool:
        # Roles are declared in apps/accounts/roles.py and applied by seed_roles;
        # one created here would have no policy behind it.
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        # System roles are defined in roles.py; deleting one would leave users
        # holding a role the policy no longer knows about.
        return not (obj is None or obj.is_system)


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ["user", "role", "granted_at", "granted_by", "revoked_at", "revoked_by"]
    list_filter = ["role", "revoked_at"]
    search_fields = ["user__email", "user__first_name", "user__last_name", "role__code"]
    autocomplete_fields = ["user", "role"]
    readonly_fields = ["granted_at", "granted_by", "revoked_by"]

    def has_delete_permission(self, request, obj=None) -> bool:
        # Revoke instead: deleting the row erases the evidence that the role was
        # ever held.
        return False
