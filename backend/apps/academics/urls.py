from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.academics.views import (
    AcademicYearViewSet,
    CalendarStatusView,
    GradeBandViewSet,
    GradingScaleViewSet,
    InstitutionViewSet,
    SemesterViewSet,
)

app_name = "academics"

router = DefaultRouter()
router.register("institution", InstitutionViewSet, basename="institution")
router.register("academic-years", AcademicYearViewSet, basename="academic-year")
router.register("semesters", SemesterViewSet, basename="semester")
router.register("grading-scales", GradingScaleViewSet, basename="grading-scale")
router.register("grade-bands", GradeBandViewSet, basename="grade-band")

urlpatterns = [
    path("calendar/", CalendarStatusView.as_view(), name="calendar-status"),
    path("", include(router.urls)),
]
