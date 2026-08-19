from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.communications.views import AnnouncementViewSet

app_name = "communications"

router = DefaultRouter()
router.register("announcements", AnnouncementViewSet, basename="announcement")

urlpatterns = [
    path("", include(router.urls)),
]
