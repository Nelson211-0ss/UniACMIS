from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.hr.views import AppraisalViewSet, ContractViewSet, LeaveRequestViewSet, PayrollExportView

app_name = "hr"

router = DefaultRouter()
router.register("contracts", ContractViewSet, basename="contract")
router.register("leave-requests", LeaveRequestViewSet, basename="leave-request")
router.register("appraisals", AppraisalViewSet, basename="appraisal")

urlpatterns = [
    path("payroll-export/", PayrollExportView.as_view(), name="payroll-export"),
    path("", include(router.urls)),
]
