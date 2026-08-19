from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.attendance.views import (
    AttendanceSummaryView,
    ExamEligibilityView,
    GrantWaiverView,
    SessionRecordViewSet,
)

app_name = "attendance"

router = DefaultRouter()
router.register("records", SessionRecordViewSet, basename="session-record")

urlpatterns = [
    path(
        "registrations/<int:registration_id>/summary/",
        AttendanceSummaryView.as_view(),
        name="summary",
    ),
    path(
        "registrations/<int:registration_id>/eligibility/",
        ExamEligibilityView.as_view(),
        name="eligibility",
    ),
    path(
        "registrations/<int:registration_id>/waive/",
        GrantWaiverView.as_view(),
        name="waive",
    ),
    path("", include(router.urls)),
]
