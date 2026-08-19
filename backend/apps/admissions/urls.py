from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.admissions.views import ApplicationViewSet, MeritListView

app_name = "admissions"

router = DefaultRouter()
router.register("applications", ApplicationViewSet, basename="application")

urlpatterns = [
    path("merit-list/", MeritListView.as_view(), name="merit-list"),
    path("", include(router.urls)),
]
