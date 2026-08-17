from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.curriculum.views import (
    CourseViewSet,
    CurriculumVersionViewSet,
    DepartmentViewSet,
    FacultyViewSet,
    ProgrammeViewSet,
)

app_name = "curriculum"

router = DefaultRouter()
router.register("faculties", FacultyViewSet, basename="faculty")
router.register("departments", DepartmentViewSet, basename="department")
router.register("programmes", ProgrammeViewSet, basename="programme")
router.register("courses", CourseViewSet, basename="course")
router.register("curriculum-versions", CurriculumVersionViewSet, basename="curriculum-version")

urlpatterns = [path("", include(router.urls))]
