"""Reporting & compliance (FR-RPT-01…05).

FR-RPT-03 (disaggregation) and FR-RPT-04 (the audit chain) landed in Phase 1
— the fields and the hash chain they depend on already exist. What is built
here is the reporting surface that reads them.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class DashboardWidget(models.Model):
    """FR-RPT-01's "configurable" dashboard: which KPI tiles show, and in
    what order, is a row a management-tier user edits — never a constant a
    developer would need to change to add or hide one."""

    key = models.CharField(_("key"), max_length=50, unique=True)
    label = models.CharField(_("label"), max_length=100)
    is_enabled = models.BooleanField(_("enabled"), default=True)
    sort_order = models.PositiveSmallIntegerField(_("sort order"), default=0)

    class Meta:
        verbose_name = _("dashboard widget")
        verbose_name_plural = _("dashboard widgets")
        ordering = ["sort_order", "key"]
        permissions = [
            ("view_dashboard", _("Can view the KPI dashboard")),
            ("export_statutoryreport", _("Can export a statutory or custom report")),
        ]

    def __str__(self) -> str:
        return self.label
