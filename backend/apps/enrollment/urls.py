from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.enrollment.views import ClassListView, CourseRegistrationViewSet, CreditSummaryView

app_name = "enrollment"

router = DefaultRouter()
router.register("registrations", CourseRegistrationViewSet, basename="registration")

urlpatterns = [
    path("class-list/", ClassListView.as_view(), name="class-list"),
    path("credit-summary/<int:student_id>/", CreditSummaryView.as_view(), name="credit-summary"),
    path("", include(router.urls)),
]
