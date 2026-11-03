from rest_framework import serializers

from .models import ROLE_PERMISSIONS, AuditLog, Role, User


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, min_length=6)
    pin = serializers.RegexField(r"^\d{4,6}$", write_only=True, required=False, allow_blank=True)
    display_name = serializers.CharField(read_only=True)
    has_pin = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "first_name", "last_name", "display_name", "email", "phone",
            "role", "is_active", "password", "pin", "has_pin", "permissions", "last_login",
        ]
        read_only_fields = ["last_login"]

    def get_has_pin(self, obj):
        return bool(obj.pin_hash)

    def get_permissions(self, obj):
        if obj.is_superuser or obj.role == Role.OWNER:
            return ["*"]
        return sorted(ROLE_PERMISSIONS.get(obj.role, set()))

    def validate(self, attrs):
        request = self.context.get("request")
        new_role = attrs.get("role")
        # Only an owner can create or promote owners.
        if new_role == Role.OWNER and request and request.user.role != Role.OWNER and not request.user.is_superuser:
            raise serializers.ValidationError({"role": "Only an owner can assign the owner role."})
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": "A password is required for new users."})
        return attrs

    def _apply_secrets(self, user, password, pin):
        if password:
            user.set_password(password)
        if pin is not None and pin != "":
            user.set_pin(pin)

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        pin = validated_data.pop("pin", None)
        user = User(**validated_data)
        self._apply_secrets(user, password, pin)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        pin = validated_data.pop("pin", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        self._apply_secrets(instance, password, pin)
        instance.save()
        return instance


class UserChoiceSerializer(serializers.ModelSerializer):
    """What the lock screen shows: who can sign in with a PIN. No sensitive fields."""

    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "display_name", "role"]


class AuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.display_name", default=None, read_only=True)
    approved_by_name = serializers.CharField(source="approved_by.display_name", default=None, read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id", "created_at", "user", "user_name", "approved_by", "approved_by_name",
            "action", "entity", "entity_id", "details",
        ]
