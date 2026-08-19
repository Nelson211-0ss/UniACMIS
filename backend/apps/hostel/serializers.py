from __future__ import annotations

from rest_framework import serializers

from apps.hostel.models import Allocation, Room


class RoomSerializer(serializers.ModelSerializer):
    available_beds = serializers.IntegerField(read_only=True)
    occupied_beds = serializers.IntegerField(read_only=True)

    class Meta:
        model = Room
        fields = [
            "id",
            "building",
            "room_number",
            "capacity",
            "gender_restriction",
            "available_beds",
            "occupied_beds",
            "is_active",
        ]


class AllocationSerializer(serializers.ModelSerializer):
    student_number = serializers.CharField(source="student.student_id", read_only=True)
    room_label = serializers.SerializerMethodField()

    class Meta:
        model = Allocation
        fields = [
            "id",
            "student",
            "student_number",
            "room",
            "room_label",
            "academic_year",
            "status",
            "allocated_at",
            "vacated_at",
            "notes",
            "created_at",
        ]
        read_only_fields = ["status", "allocated_at", "vacated_at", "created_at"]

    def get_room_label(self, obj: Allocation) -> str:
        return str(obj.room)


class AllocateSerializer(serializers.Serializer):
    student = serializers.IntegerField()
    room = serializers.IntegerField()
    academic_year = serializers.IntegerField()


class VacateSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=2000)
