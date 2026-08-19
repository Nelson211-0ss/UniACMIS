from __future__ import annotations

from django.db.models import Q, QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.mixins import ScopedQuerysetMixin
from apps.core.exceptions import error_envelope
from apps.core.mixins import CreateWithResponseSerializerMixin
from apps.core.permissions import HasModulePermission
from apps.timetabling import services
from apps.timetabling.models import ExamTimetable, Room, TimetableEntry
from apps.timetabling.serializers import (
    ExamTimetableSerializer,
    PublishResultSerializer,
    RoomSerializer,
    TimetableEntrySerializer,
)


class RoomViewSet(viewsets.ModelViewSet):
    """The room inventory a timetable is built against."""

    queryset = Room.objects.all()
    serializer_class = RoomSerializer
    permission_classes = [HasModulePermission]
    required_permissions = {
        "GET": "timetabling.view_room",
        "POST": "timetabling.add_room",
        "PUT": "timetabling.change_room",
        "PATCH": "timetabling.change_room",
        "DELETE": "timetabling.delete_room",
    }
    filterset_fields = ["is_active", "building"]
    ordering = ["code"]

    def perform_create(self, serializer) -> None:
        data = serializer.validated_data
        serializer.instance = services.create_room(
            code=data["code"],
            name=data["name"],
            building=data.get("building", ""),
            capacity=data.get("capacity", 0),
            actor=self.request.user,
        )

    def perform_update(self, serializer) -> None:
        data = serializer.validated_data
        serializer.instance = services.update_room(
            serializer.instance,
            name=data.get("name"),
            building=data.get("building"),
            capacity=data.get("capacity"),
            is_active=data.get("is_active"),
            actor=self.request.user,
        )


class TimetableEntryViewSet(
    ScopedQuerysetMixin, CreateWithResponseSerializerMixin, viewsets.ModelViewSet
):
    """The recurring weekly class timetable (FR-TT-01…03).

    The registrar builds and publishes it; a lecturer sees their own slots plus
    everything already published; a HOD sees their whole department, published
    or not, to review before publish; a student sees only what is published —
    the same "draft vs. released" boundary FR-TT-03 exists to enforce.
    """

    queryset = TimetableEntry.objects.select_related("course", "room", "lecturer__user")
    serializer_class = TimetableEntrySerializer
    response_serializer_class = TimetableEntrySerializer
    permission_classes = [HasModulePermission]
    required_permissions = {
        "GET": "timetabling.view_timetableentry",
        "POST": "timetabling.add_timetableentry",
        "PUT": "timetabling.change_timetableentry",
        "PATCH": "timetabling.change_timetableentry",
        "DELETE": "timetabling.delete_timetableentry",
    }
    filterset_fields = ["semester", "course", "room", "lecturer", "day_of_week", "is_published"]
    ordering = ["day_of_week", "start_time"]

    unscoped_roles = {"registrar", "ict_admin", "management"}
    scope_methods = {
        "student": "scope_to_published",
        "lecturer": "scope_to_own_or_published",
        "hod": "scope_to_department",
    }

    def scope_to_published(self, queryset: QuerySet, user) -> QuerySet:
        return queryset.filter(is_published=True)

    def scope_to_own_or_published(self, queryset: QuerySet, user) -> QuerySet:
        return queryset.filter(Q(lecturer__user=user) | Q(is_published=True))

    def scope_to_department(self, queryset: QuerySet, user) -> QuerySet:
        profile = getattr(user, "staff_profile", None)
        if profile is None or profile.department_id is None:
            return queryset.none()
        return queryset.filter(course__department_id=profile.department_id)

    def perform_create(self, serializer) -> None:
        data = serializer.validated_data
        entry = services.create_entry(
            course_id=data["course"].pk,
            semester_id=data["semester"].pk,
            day_of_week=data["day_of_week"],
            start_time=data["start_time"],
            end_time=data["end_time"],
            room_id=data["room"].pk if data.get("room") else None,
            lecturer_id=data["lecturer"].pk if data.get("lecturer") else None,
            actor=self.request.user,
        )
        serializer.instance = entry

    def perform_update(self, serializer) -> None:
        data = serializer.validated_data
        entry = services.update_entry(
            serializer.instance,
            day_of_week=data.get("day_of_week"),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            room_id=data["room"].pk if data.get("room") else None,
            lecturer_id=data["lecturer"].pk if data.get("lecturer") else None,
            actor=self.request.user,
        )
        serializer.instance = entry

    @extend_schema(
        summary="Publish the class timetable for a semester",
        responses={200: PublishResultSerializer},
    )
    @action(detail=False, methods=["post"], url_path="publish")
    def publish(self, request: Request) -> Response:
        if not request.user.has_perm("timetabling.change_timetableentry"):
            return Response(
                error_envelope("permission_denied", "You may not publish the timetable."),
                status=403,
            )
        semester_id = request.data.get("semester")
        if not semester_id:
            return Response(error_envelope("bad_request", "`semester` is required."), status=400)
        count = services.publish_timetable(int(semester_id), request.user)
        return Response(PublishResultSerializer({"published_count": count}).data)


class ExamTimetableViewSet(
    ScopedQuerysetMixin, CreateWithResponseSerializerMixin, viewsets.ModelViewSet
):
    """The exam timetable (FR-TT-04) — the examinations office's schedule,
    with invigilator assignment."""

    queryset = ExamTimetable.objects.select_related("course", "room").prefetch_related(
        "invigilators__user"
    )
    serializer_class = ExamTimetableSerializer
    response_serializer_class = ExamTimetableSerializer
    permission_classes = [HasModulePermission]
    required_permissions = {
        "GET": "timetabling.view_examtimetable",
        "POST": "timetabling.add_examtimetable",
        "PUT": "timetabling.change_examtimetable",
        "PATCH": "timetabling.change_examtimetable",
        "DELETE": "timetabling.delete_examtimetable",
    }
    filterset_fields = ["semester", "course", "room", "is_published"]
    ordering = ["exam_date", "start_time"]

    unscoped_roles = {"registrar", "ict_admin", "management", "examinations"}
    scope_methods = {
        "student": "scope_to_published",
        "lecturer": "scope_to_published",
        "hod": "scope_to_department",
    }

    def scope_to_published(self, queryset: QuerySet, user) -> QuerySet:
        return queryset.filter(is_published=True)

    def scope_to_department(self, queryset: QuerySet, user) -> QuerySet:
        profile = getattr(user, "staff_profile", None)
        if profile is None or profile.department_id is None:
            return queryset.none()
        return queryset.filter(course__department_id=profile.department_id)

    def perform_create(self, serializer) -> None:
        data = serializer.validated_data
        entry = services.create_exam_entry(
            course_id=data["course"].pk,
            semester_id=data["semester"].pk,
            exam_date=data["exam_date"],
            start_time=data["start_time"],
            end_time=data["end_time"],
            room_id=data["room"].pk if data.get("room") else None,
            invigilator_ids=[s.pk for s in data.get("invigilators", [])],
            actor=self.request.user,
        )
        serializer.instance = entry

    def perform_update(self, serializer) -> None:
        data = serializer.validated_data
        invigilators = data.get("invigilators")
        entry = services.update_exam_entry(
            serializer.instance,
            exam_date=data.get("exam_date"),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            room_id=data["room"].pk if data.get("room") else None,
            invigilator_ids=[s.pk for s in invigilators] if invigilators is not None else None,
            actor=self.request.user,
        )
        serializer.instance = entry

    @extend_schema(
        summary="Publish the exam timetable for a semester",
        responses={200: PublishResultSerializer},
    )
    @action(detail=False, methods=["post"], url_path="publish")
    def publish(self, request: Request) -> Response:
        if not request.user.has_perm("timetabling.change_examtimetable"):
            return Response(
                error_envelope("permission_denied", "You may not publish the exam timetable."),
                status=403,
            )
        semester_id = request.data.get("semester")
        if not semester_id:
            return Response(error_envelope("bad_request", "`semester` is required."), status=400)
        count = services.publish_exam_timetable(int(semester_id), request.user)
        return Response(PublishResultSerializer({"published_count": count}).data)
