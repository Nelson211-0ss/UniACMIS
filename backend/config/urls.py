"""
Root URL configuration.

Everything the frontend consumes lives under /api/v1/. Breaking changes get a
/api/v2/ rather than a silent change of shape.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.core.views import HealthCheckView

admin.site.site_header = "UniACMIS Administration"
admin.site.site_title = "UniACMIS"
admin.site.index_title = "Academic Management Information System"

api_v1 = [
    path("auth/", include("apps.accounts.urls")),
    path("academics/", include("apps.academics.urls")),
    path("curriculum/", include("apps.curriculum.urls")),
    path("registry/", include("apps.registry.urls")),
    path("sync/", include("apps.core.sync.urls")),
    path("audit/", include("apps.audit.urls")),
    # Schema and docs
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include((api_v1, "v1"), namespace="v1")),
    # Unauthenticated: lets a campus monitor detect an unhealthy instance.
    path("healthz/", HealthCheckView.as_view(), name="healthz"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
