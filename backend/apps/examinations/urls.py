from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.examinations.views import (
    AssessmentViewSet,
    CourseResultView,
    GradeAppealViewSet,
    MarkViewSet,
    MissingMarksView,
    ResultApprovalViewSet,
    StudentResultView,
)

app_name = "examinations"

router = DefaultRouter()
router.register("assessments", AssessmentViewSet, basename="assessment")
router.register("marks", MarkViewSet, basename="mark")
router.register("appeals", GradeAppealViewSet, basename="grade-appeal")
router.register("approvals", ResultApprovalViewSet, basename="result-approval")

urlpatterns = [
    path("missing-marks/", MissingMarksView.as_view(), name="missing-marks"),
    path(
        "registrations/<int:registration_id>/result/",
        CourseResultView.as_view(),
        name="course-result",
    ),
    path(
        "students/<int:student_id>/semesters/<int:semester_id>/result/",
        StudentResultView.as_view(),
        name="student-result",
    ),
    path("", include(router.urls)),
]
