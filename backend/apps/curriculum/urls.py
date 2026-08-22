from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.curriculum.views import (
    CourseViewSet,
    CurriculumCourseViewSet,
    CurriculumVersionViewSet,
    DepartmentViewSet,
    FacultyViewSet,
    PrerequisiteViewSet,
    ProgrammeViewSet,
)

app_name = "curriculum"

router = DefaultRouter()
router.register("faculties", FacultyViewSet, basename="faculty")
router.register("departments", DepartmentViewSet, basename="department")
router.register("programmes", ProgrammeViewSet, basename="programme")
router.register("courses", CourseViewSet, basename="course")
router.register("curriculum-versions", CurriculumVersionViewSet, basename="curriculum-version")
router.register("curriculum-courses", CurriculumCourseViewSet, basename="curriculum-course")
router.register("prerequisites", PrerequisiteViewSet, basename="prerequisite")

urlpatterns = [path("", include(router.urls))]
