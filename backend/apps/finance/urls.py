from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.finance.views import (
    DefaulterReportView,
    FeeBalanceView,
    FeeStructureViewSet,
    InvoiceViewSet,
    PaymentViewSet,
    PaymentWebhookView,
    RefundViewSet,
    ScholarshipViewSet,
)

app_name = "finance"

router = DefaultRouter()
router.register("fee-structures", FeeStructureViewSet, basename="fee-structure")
router.register("invoices", InvoiceViewSet, basename="invoice")
router.register("payments", PaymentViewSet, basename="payment")
router.register("scholarships", ScholarshipViewSet, basename="scholarship")
router.register("refunds", RefundViewSet, basename="refund")

urlpatterns = [
    path("reports/defaulters/", DefaulterReportView.as_view(), name="defaulter-report"),
    path("students/<int:student_id>/balance/", FeeBalanceView.as_view(), name="student-balance"),
    path("webhooks/payment/", PaymentWebhookView.as_view(), name="payment-webhook"),
    path("", include(router.urls)),
]
