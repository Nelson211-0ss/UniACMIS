from __future__ import annotations

from rest_framework import serializers

from apps.timetabling.models import ExamTimetable, Room, TimetableEntry


class RoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = ["id", "code", "name", "building", "capacity", "is_active"]


class TimetableEntrySerializer(serializers.ModelSerializer):
    course_code = serializers.CharField(source="course.code", read_only=True)
    course_title = serializers.CharField(source="course.title", read_only=True)
    room_code = serializers.CharField(source="room.code", read_only=True, default="")
    lecturer_name = serializers.CharField(
        source="lecturer.user.get_full_name", read_only=True, default=""
    )
    day_of_week_display = serializers.CharField(source="get_day_of_week_display", read_only=True)

    class Meta:
        model = TimetableEntry
        fields = [
            "id",
            "course",
            "course_code",
            "course_title",
            "semester",
            "room",
            "room_code",
            "lecturer",
            "lecturer_name",
            "day_of_week",
            "day_of_week_display",
            "start_time",
            "end_time",
            "is_published",
            "published_at",
        ]
        read_only_fields = ["is_published", "published_at"]


class ExamTimetableSerializer(serializers.ModelSerializer):
    course_code = serializers.CharField(source="course.code", read_only=True)
    course_title = serializers.CharField(source="course.title", read_only=True)
    room_code = serializers.CharField(source="room.code", read_only=True, default="")
    invigilator_names = serializers.SerializerMethodField()

    class Meta:
        model = ExamTimetable
        fields = [
            "id",
            "course",
            "course_code",
            "course_title",
            "semester",
            "room",
            "room_code",
            "invigilators",
            "invigilator_names",
            "exam_date",
            "start_time",
            "end_time",
            "is_published",
            "published_at",
        ]
        read_only_fields = ["is_published", "published_at"]
        extra_kwargs = {"invigilators": {"required": False}}

    def get_invigilator_names(self, obj: ExamTimetable) -> list[str]:
        return [i.user.get_full_name() for i in obj.invigilators.all()]


class PublishResultSerializer(serializers.Serializer):
    published_count = serializers.IntegerField()
