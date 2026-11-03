from rest_framework import serializers

from .models import CashMovement, Shift


class CashMovementSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.display_name", read_only=True, default=None)
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = CashMovement
        fields = ["id", "kind", "kind_label", "amount", "reason", "user_name", "created_at"]


class ShiftSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.display_name", read_only=True)
    closed_by_name = serializers.CharField(source="closed_by.display_name", read_only=True, default=None)

    class Meta:
        model = Shift
        fields = ["id", "user", "user_name", "register_name", "status", "opened_at", "closed_at",
                  "opening_float", "expected_cash", "counted_cash", "difference", "closing_note",
                  "closed_by_name"]
