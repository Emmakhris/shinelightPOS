from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.accounts.permissions import HasPerm
from apps.accounts.services import audit, require_permission_or_approval

from .models import CashMovement, Shift
from .serializers import CashMovementSerializer, ShiftSerializer
from .services import add_cash_movement, close_shift, current_shift, open_shift, shift_report


@api_view(["GET"])
@permission_classes([HasPerm("sell")])
def current(request):
    shift = current_shift(request.user)
    return Response(ShiftSerializer(shift).data if shift else None)


@api_view(["POST"])
@permission_classes([HasPerm("sell")])
def open_(request):
    shift = open_shift(
        request.user, request.data.get("opening_float") or 0, request.data.get("register_name") or "Till 1"
    )
    audit("shift_opened", request.user, "shift", shift.pk, opening_float=str(shift.opening_float))
    return Response(ShiftSerializer(shift).data, status=status.HTTP_201_CREATED)


class ShiftViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = ShiftSerializer
    filterset_fields = {"status": ["exact"], "user": ["exact"], "opened_at": ["gte", "lte"]}

    def get_queryset(self):
        qs = Shift.objects.select_related("user", "closed_by")
        if not self.request.user.has_pos_perm("manage_shifts"):
            qs = qs.filter(user=self.request.user)  # cashiers see only their own shifts
        return qs

    @action(detail=True, methods=["get"])
    def report(self, request, pk=None):
        shift = self.get_object()
        return Response(shift.report if shift.report else shift_report(shift))

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        shift = self.get_object()
        if shift.user != request.user and not request.user.has_pos_perm("manage_shifts"):
            raise PermissionDenied("Only the cashier or a manager can close this shift.")
        if request.data.get("counted_cash") in (None, ""):
            return Response({"detail": "Enter the cash you counted."}, status=status.HTTP_400_BAD_REQUEST)
        shift = close_shift(shift, request.data["counted_cash"], request.user, request.data.get("note", ""))
        audit("shift_closed", request.user, "shift", shift.pk, expected=str(shift.expected_cash),
              counted=str(shift.counted_cash), difference=str(shift.difference))
        return Response(shift.report)

    @action(detail=True, methods=["get", "post"], url_path="cash-movements")
    def cash_movements(self, request, pk=None):
        shift = self.get_object()
        if request.method == "GET":
            return Response(CashMovementSerializer(shift.cash_movements.select_related("user"), many=True).data)
        kind = request.data.get("kind")
        if kind not in CashMovement.Kind.values:
            return Response({"detail": "Unknown cash movement."}, status=status.HTTP_400_BAD_REQUEST)
        approver = require_permission_or_approval(request.user, "cash_movement", request.data.get("approval_pin"))
        movement = add_cash_movement(
            shift, kind, request.data.get("amount"), request.data.get("reason") or "", request.user, approver
        )
        audit(f"cash_{kind}", request.user, "shift", shift.pk, approved_by=approver,
              amount=str(movement.amount), reason=movement.reason)
        return Response(CashMovementSerializer(movement).data, status=status.HTTP_201_CREATED)
