from __future__ import annotations

from django.contrib import admin

from apps.reporting.models import DashboardWidget


@admin.register(DashboardWidget)
class DashboardWidgetAdmin(admin.ModelAdmin):
    list_display = ["key", "label", "is_enabled", "sort_order"]
    list_editable = ["is_enabled", "sort_order"]
