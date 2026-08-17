from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.registry.views import SponsorViewSet, StaffProfileViewSet, StudentViewSet

app_name = "registry"

router = DefaultRouter()
router.register("students", StudentViewSet, basename="student")
router.register("sponsors", SponsorViewSet, basename="sponsor")
router.register("staff", StaffProfileViewSet, basename="staff")

urlpatterns = [path("", include(router.urls))]
