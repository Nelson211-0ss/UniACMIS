from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.alumni.views import AlumniEventViewSet, AlumniProfileViewSet

app_name = "alumni"

router = DefaultRouter()
router.register("profiles", AlumniProfileViewSet, basename="alumni-profile")
router.register("events", AlumniEventViewSet, basename="alumni-event")

urlpatterns = [
    path("", include(router.urls)),
]
