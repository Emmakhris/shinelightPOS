from django.contrib.auth import authenticate
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from .models import AuditLog, Role, User
from .permissions import HasPerm
from .serializers import AuditLogSerializer, UserChoiceSerializer, UserSerializer
from .services import audit, find_approver


class LoginThrottle(ScopedRateThrottle):
    scope = "login"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


def _tokens_for(user, request):
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": UserSerializer(user, context={"request": request}).data,
    }


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginThrottle])
def login(request):
    user = authenticate(
        request, username=request.data.get("username", ""), password=request.data.get("password", "")
    )
    if user is None or not user.is_active:
        return Response({"detail": "Wrong username or password."}, status=status.HTTP_401_UNAUTHORIZED)
    audit("login", user=user)
    return Response(_tokens_for(user, request))


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginThrottle])
def pin_login(request):
    """Quick cashier switch on a shared till: pick your name, type your PIN."""
    user = User.objects.filter(pk=request.data.get("user_id"), is_active=True).first()
    if user is None or not user.check_pin(request.data.get("pin")):
        return Response({"detail": "Wrong PIN."}, status=status.HTTP_401_UNAUTHORIZED)
    audit("pin_login", user=user)
    return Response(_tokens_for(user, request))


@api_view(["GET"])
@permission_classes([AllowAny])
def pin_users(request):
    users = User.objects.filter(is_active=True).exclude(pin_hash="")
    return Response(UserChoiceSerializer(users, many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(UserSerializer(request.user, context={"request": request}).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def verify_approval(request):
    """Let the till check a manager PIN before sending the real request."""
    approver = find_approver(request.data.get("pin"))
    perm = request.data.get("permission")
    if approver is None or (perm and not approver.has_pos_perm(perm)):
        return Response({"detail": "PIN not accepted."}, status=status.HTTP_403_FORBIDDEN)
    return Response({"approver": approver.display_name})


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [HasPerm("manage_users")]
    search_fields = ["username", "first_name", "last_name"]
    filterset_fields = ["role", "is_active"]

    def get_queryset(self):
        return User.objects.all()

    def perform_create(self, serializer):
        user = serializer.save()
        audit("user_created", self.request.user, "user", user.pk, role=user.role)

    def perform_update(self, serializer):
        user = serializer.save()
        audit("user_updated", self.request.user, "user", user.pk, role=user.role, is_active=user.is_active)

    def destroy(self, request, *args, **kwargs):
        # Users are referenced by sales and logs; deactivate rather than delete.
        user = self.get_object()
        if user == request.user:
            return Response({"detail": "You cannot deactivate yourself."}, status=status.HTTP_400_BAD_REQUEST)
        if user.role == Role.OWNER and not User.objects.filter(role=Role.OWNER, is_active=True).exclude(pk=user.pk).exists():
            return Response({"detail": "There must be at least one active owner."}, status=status.HTTP_400_BAD_REQUEST)
        user.is_active = False
        user.save(update_fields=["is_active"])
        audit("user_deactivated", request.user, "user", user.pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AuditLogViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = AuditLogSerializer
    permission_classes = [HasPerm("view_audit")]
    filterset_fields = ["action", "user"]
    search_fields = ["action", "entity", "entity_id"]

    def get_queryset(self):
        return AuditLog.objects.select_related("user", "approved_by")
