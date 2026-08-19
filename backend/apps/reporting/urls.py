from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.reporting.views import (
    DashboardView,
    DashboardWidgetViewSet,
    PassRateReportView,
    ReportExportView,
)

app_name = "reporting"

router = DefaultRouter()
router.register("widgets", DashboardWidgetViewSet, basename="dashboard-widget")

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("pass-rate/", PassRateReportView.as_view(), name="pass-rate"),
    path("reports/<str:key>/export/", ReportExportView.as_view(), name="report-export"),
    path("", include(router.urls)),
]
