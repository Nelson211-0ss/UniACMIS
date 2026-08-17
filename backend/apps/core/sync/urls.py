from django.urls import path

from apps.core.sync.views import (
    SyncBatchView,
    SyncConflictListView,
    SyncConflictResolveView,
    SyncEntitiesView,
    SyncOperationView,
)

app_name = "sync"

urlpatterns = [
    path("batch/", SyncBatchView.as_view(), name="batch"),
    path("operations/", SyncOperationView.as_view(), name="operations"),
    path("entities/", SyncEntitiesView.as_view(), name="entities"),
    path("conflicts/", SyncConflictListView.as_view(), name="conflict-list"),
    path("conflicts/<int:pk>/resolve/", SyncConflictResolveView.as_view(), name="conflict-resolve"),
]
