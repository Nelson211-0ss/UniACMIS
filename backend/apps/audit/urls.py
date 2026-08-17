from django.urls import path

from apps.audit.views import AuditChainVerificationView, AuditLogListView

app_name = "audit"

urlpatterns = [
    path("entries/", AuditLogListView.as_view(), name="entry-list"),
    path("verify-chain/", AuditChainVerificationView.as_view(), name="verify-chain"),
]
