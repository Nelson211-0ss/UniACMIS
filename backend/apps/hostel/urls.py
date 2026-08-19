from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.hostel.views import AllocationViewSet, RoomViewSet

app_name = "hostel"

router = DefaultRouter()
router.register("rooms", RoomViewSet, basename="room")
router.register("allocations", AllocationViewSet, basename="allocation")

urlpatterns = [
    path("", include(router.urls)),
]
