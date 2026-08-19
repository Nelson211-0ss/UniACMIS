from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.documents.views import (
    GraduationClearanceView,
    IssuedDocumentViewSet,
    TranscriptRequestViewSet,
    VerifyDocumentView,
)

app_name = "documents"

router = DefaultRouter()
router.register("transcript-requests", TranscriptRequestViewSet, basename="transcript-request")
router.register("issued", IssuedDocumentViewSet, basename="issued-document")

urlpatterns = [
    # A serial number is itself "TRX/2026/00001" — the `path` converter is
    # required so the embedded slashes are not mistaken for extra segments.
    path("verify/<path:serial_number>/", VerifyDocumentView.as_view(), name="verify"),
    path(
        "students/<int:student_id>/clearance/", GraduationClearanceView.as_view(), name="clearance"
    ),
    path("", include(router.urls)),
]
