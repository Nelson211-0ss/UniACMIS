"""
Identity and role assignment.

Permissions are never attached to a user directly. A user holds roles; a role
maps to a Django group; the group carries the permissions. That gives exactly one
place to read an authorisation decision from, and makes "what can a bursar do?" a
question with a single answer (NFR-SEC-01).
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, Group, PermissionsMixin
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditedModel
from apps.core.models import TimeStampedModel


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("is_active", True)
        if not extra["is_staff"] or not extra["is_superuser"]:
            raise ValueError("A superuser must have is_staff and is_superuser set.")
        return self._create_user(email, password, **extra)

    def get_by_natural_key(self, username: str | None):
        # Case-insensitive sign-in: staff type their address inconsistently and
        # being locked out over a capital letter is a support call nobody needs.
        return self.get(email__iexact=username)


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel, AuditedModel):
    """Login identity for staff and students alike.

    Email is the credential rather than a username: everyone issued an account
    here has an address, and password reset needs one anyway.
    """

    audit_fields = ("email", "is_active", "is_staff", "is_superuser", "mfa_enabled")

    email = models.EmailField(_("email address"), unique=True)

    first_name = models.CharField(_("first name"), max_length=100)
    # Kept as its own column: a paternal or grandfather name is normal here and
    # must appear correctly on a certificate, so it cannot be folded into either
    # of the other two.
    middle_name = models.CharField(_("middle name"), max_length=100, blank=True)
    last_name = models.CharField(_("last name"), max_length=100)

    phone = models.CharField(
        _("phone number"),
        max_length=32,
        blank=True,
        help_text=_("E.164 format. The primary channel for critical notices."),
    )

    is_active = models.BooleanField(_("active"), default=True)
    is_staff = models.BooleanField(
        _("Django admin access"),
        default=False,
        help_text=_("Grants access to the admin site. Unrelated to being a staff member."),
    )

    # NFR-SEC-04: MFA is available to any account; enrolment is opt-in, not
    # forced on any particular role. `mfa_secret` is deliberately absent from
    # `audit_fields` below — a live TOTP secret must never be written into the
    # append-only, more-widely-read audit trail.
    mfa_enabled = models.BooleanField(_("MFA enabled"), default=False)
    mfa_secret = models.CharField(_("MFA secret"), max_length=64, blank=True)

    must_change_password = models.BooleanField(
        _("must change password"),
        default=False,
        help_text=_("Set on accounts created by staff, and on all seeded accounts."),
    )

    last_login_ip = models.GenericIPAddressField(_("last login IP"), null=True, blank=True)
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["last_name", "first_name"]
        constraints = [
            # unique=True is case-sensitive in PostgreSQL, which would allow
            # A@x.com and a@x.com to coexist as two accounts.
            models.UniqueConstraint(Lower("email"), name="unique_user_email_ci"),
        ]

    def __str__(self) -> str:
        return f"{self.get_full_name()} <{self.email}>"

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        return super().save(*args, **kwargs)

    def get_full_name(self) -> str:
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join(p for p in parts if p).strip()

    def get_short_name(self) -> str:
        return self.first_name

    # ------------------------------------------------------------------ roles

    def active_roles(self):
        return Role.objects.filter(
            user_assignments__user=self, user_assignments__revoked_at__isnull=True
        ).distinct()

    def role_codes(self) -> list[str]:
        return sorted(self.active_roles().values_list("code", flat=True))

    def primary_role_code(self) -> str:
        """Role recorded on audit entries. Deterministic so the trail reads
        consistently for a user holding more than one role."""
        codes = self.role_codes()
        if self.is_superuser:
            return "superuser"
        return codes[0] if codes else ""

    def has_role(self, *codes: str) -> bool:
        return bool(set(codes) & set(self.role_codes()))

    # ----------------------------------------------------------------- lockout

    @property
    def is_locked_out(self) -> bool:
        return self.locked_until is not None and self.locked_until > timezone.now()


class MFABackupCode(models.Model):
    """One-time recovery codes issued when MFA is enabled (NFR-SEC-04) — for
    the case a phone with the authenticator app is lost. Hashed with the same
    hasher a password gets, never stored or logged in the clear, and each
    consumed exactly once."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="mfa_backup_codes")
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(default=timezone.now)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("MFA backup code")
        verbose_name_plural = _("MFA backup codes")

    def __str__(self) -> str:
        status = "used" if self.used_at else "unused"
        return f"{self.user_id} backup code [{status}]"


class Role(TimeStampedModel):
    """A named set of permissions, backed by a Django group.

    The group is the mechanism; the role is the label staff recognise and the
    thing `seed_roles` manages.
    """

    code = models.SlugField(_("code"), max_length=50, unique=True)
    name = models.CharField(_("name"), max_length=100)
    description = models.TextField(_("description"), blank=True)
    group = models.OneToOneField(
        Group, on_delete=models.CASCADE, related_name="role", null=True, blank=True
    )
    is_system = models.BooleanField(
        _("system role"),
        default=True,
        help_text=_("System roles are defined in code and cannot be deleted."),
    )

    class Meta:
        verbose_name = _("role")
        verbose_name_plural = _("roles")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class UserRole(models.Model):
    """A role grant.

    A through-model rather than a plain many-to-many because *who* granted a role
    and *when* is security-relevant in its own right — a quietly self-granted
    finance role is precisely what an auditor looks for. Revocations are recorded,
    never deleted.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="role_assignments")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="user_assignments")

    granted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="roles_granted",
    )
    granted_at = models.DateTimeField(default=timezone.now)
    revoked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="roles_revoked",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = _("role assignment")
        verbose_name_plural = _("role assignments")
        ordering = ["-granted_at"]
        constraints = [
            # One *active* grant per user and role; historical revoked grants may
            # repeat, which is what keeps the history intact.
            models.UniqueConstraint(
                fields=["user", "role"],
                condition=models.Q(revoked_at__isnull=True),
                name="unique_active_user_role",
            ),
        ]

    def __str__(self) -> str:
        state = "revoked" if self.revoked_at else "active"
        return f"{self.user.email} → {self.role.code} ({state})"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None
