from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.library.views import LibraryItemViewSet, LoanViewSet

app_name = "library"

router = DefaultRouter()
router.register("items", LibraryItemViewSet, basename="library-item")
router.register("loans", LoanViewSet, basename="loan")

urlpatterns = [
    path("", include(router.urls)),
]
