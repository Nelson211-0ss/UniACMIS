from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.timetabling.views import ExamTimetableViewSet, RoomViewSet, TimetableEntryViewSet

app_name = "timetabling"

router = DefaultRouter()
router.register("rooms", RoomViewSet, basename="room")
router.register("entries", TimetableEntryViewSet, basename="timetable-entry")
router.register("exam-entries", ExamTimetableViewSet, basename="exam-timetable-entry")

urlpatterns = [
    path("", include(router.urls)),
]
