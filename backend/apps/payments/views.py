import json

from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.accounts.permissions import HasPerm
from apps.accounts.services import audit, require_permission_or_approval
from apps.common.exceptions import BusinessError

from . import paystack
from .models import PaystackCharge, PaystackRefund
from .serializers import PaystackRefundSerializer


class ChargeSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    invoice_number = serializers.CharField(source="payment.sale.invoice_number", read_only=True, default=None)
    sale = serializers.IntegerField(source="payment.sale_id", read_only=True, default=None)
    created_by_name = serializers.CharField(source="created_by.display_name", read_only=True, default=None)
    refunds = PaystackRefundSerializer(many=True, read_only=True)

    class Meta:
        model = PaystackCharge
        fields = ["reference", "amount", "currency", "phone", "network", "status", "status_label", "display_text",
                  "message", "created_at", "paid_at", "invoice_number", "sale", "created_by_name", "refunds"]


class StartChargeInput(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    phone = serializers.CharField(max_length=20)
    network = serializers.ChoiceField(choices=list(paystack.PAYSTACK_PROVIDERS))


def _require_enabled():
    if not paystack.enabled():
        raise BusinessError("Paystack is not set up. Add PAYSTACK_SECRET_KEY to backend\\.env.")


def _get_charge(request, reference):
    charge = get_object_or_404(PaystackCharge.objects.select_related("payment__sale", "created_by"), reference=reference)
    if charge.created_by_id != request.user.pk and not request.user.has_pos_perm("view_reports"):
        raise BusinessError("This payment was started by someone else.", http_status=status.HTTP_403_FORBIDDEN)
    return charge


@api_view(["GET", "POST"])
@permission_classes([HasPerm("sell")])
def momo(request):
    if request.method == "POST":
        _require_enabled()
        s = StartChargeInput(data=request.data)
        s.is_valid(raise_exception=True)
        charge = paystack.start_momo_charge(request.user, **s.validated_data)
        audit("paystack_momo_started", request.user, "paystack_charge", charge.reference,
              amount=str(charge.amount), network=charge.network, status=charge.status)
        return Response(ChargeSerializer(charge).data, status=status.HTTP_201_CREATED)
    qs = PaystackCharge.objects.select_related("payment__sale", "created_by")
    if not request.user.has_pos_perm("view_reports"):
        qs = qs.filter(created_by=request.user)
    params = request.query_params
    if params.get("start"):
        qs = qs.filter(created_at__date__gte=params["start"])
    if params.get("end"):
        qs = qs.filter(created_at__date__lte=params["end"])
    if params.get("unmatched"):
        qs = qs.filter(status=PaystackCharge.Status.SUCCESS, payment__isnull=True, refunds__isnull=True)
    return Response(ChargeSerializer(qs[:500], many=True).data)


@api_view(["GET"])
@permission_classes([HasPerm("sell")])
def momo_detail(request, reference):
    """Latest status. The till polls this while the customer approves on their phone."""
    charge = _get_charge(request, reference)
    if charge.status != PaystackCharge.Status.SUCCESS:
        charge = paystack.check_charge(charge, force=request.query_params.get("force") == "1")
    return Response(ChargeSerializer(charge).data)


@api_view(["POST"])
@permission_classes([HasPerm("sell")])
def momo_otp(request, reference):
    charge = _get_charge(request, reference)
    charge = paystack.submit_otp(charge, request.data.get("otp", ""))
    return Response(ChargeSerializer(charge).data)


@api_view(["POST"])
@permission_classes([HasPerm("sell")])
def momo_cancel(request, reference):
    """Stop waiting at the till. If the customer approves anyway it shows as unmatched in reports."""
    charge = _get_charge(request, reference)
    if charge.status == PaystackCharge.Status.SUCCESS:
        raise BusinessError("This payment has already been made and cannot be cancelled here.")
    charge.status = PaystackCharge.Status.ABANDONED
    charge.save(update_fields=["status", "updated_at"])
    return Response(ChargeSerializer(charge).data)


@api_view(["POST"])
@permission_classes([HasPerm("sell")])
def momo_refund(request, reference):
    """Send back money that was received but never reached a sale."""
    _require_enabled()
    charge = get_object_or_404(PaystackCharge, reference=reference)
    reason = (request.data.get("reason") or "").strip()
    if not reason:
        raise BusinessError("Give a reason for the refund.")
    approver = require_permission_or_approval(
        request.user, "refund", request.data.get("approval_pin"), "Refunds need manager approval."
    )
    refund = paystack.refund_unmatched_charge(request.user, charge, reason, approver)
    audit("paystack_refund", request.user, "paystack_charge", charge.reference, approved_by=approver,
          amount=str(refund.amount), reason=reason)
    return Response(PaystackRefundSerializer(paystack.send_refund(refund)).data, status=status.HTTP_201_CREATED)


def _get_refund(reference):
    _require_enabled()
    return get_object_or_404(PaystackRefund.objects.select_related("charge", "sale_refund__sale", "created_by"),
                             reference=reference)


@api_view(["GET"])
@permission_classes([HasPerm("view_reports")])
def refunds(request):
    qs = PaystackRefund.objects.select_related("charge", "sale_refund__sale", "created_by")
    params = request.query_params
    if params.get("start"):
        qs = qs.filter(created_at__date__gte=params["start"])
    if params.get("end"):
        qs = qs.filter(created_at__date__lte=params["end"])
    return Response(PaystackRefundSerializer(qs[:500], many=True).data)


@api_view(["POST"])
@permission_classes([HasPerm("sell")])
def refund_check(request, reference):
    return Response(PaystackRefundSerializer(paystack.check_refund(_get_refund(reference))).data)


@api_view(["POST"])
@permission_classes([HasPerm("sell")])
def refund_retry(request, reference):
    refund = _get_refund(reference)
    approver = require_permission_or_approval(
        request.user, "refund", request.data.get("approval_pin"), "Refunds need manager approval."
    )
    old_reference = refund.reference
    refund = paystack.retry_refund(refund)
    audit("paystack_refund_retried", request.user, "paystack_refund", refund.reference, approved_by=approver,
          previous=old_reference, status=refund.status)
    return Response(PaystackRefundSerializer(refund).data)


@api_view(["POST"])
@permission_classes([HasPerm("sell")])
def refund_settle(request, reference):
    """The customer was paid another way, e.g. by cash or a direct MoMo transfer."""
    refund = _get_refund(reference)
    note = (request.data.get("note") or "").strip()
    if not note:
        raise BusinessError("Say how the customer was paid.")
    approver = require_permission_or_approval(
        request.user, "refund", request.data.get("approval_pin"), "Refunds need manager approval."
    )
    refund = paystack.settle_refund(refund, note)
    audit("paystack_refund_settled", request.user, "paystack_refund", refund.reference, approved_by=approver,
          amount=str(refund.amount), note=note)
    return Response(PaystackRefundSerializer(refund).data)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def webhook(request):
    """Paystack calls this when it can reach the server (needs a public URL)."""
    raw = request.body
    if not paystack.valid_signature(raw, request.headers.get("x-paystack-signature", "")):
        return Response(status=status.HTTP_401_UNAUTHORIZED)
    try:
        paystack.handle_webhook(json.loads(raw.decode() or "{}"))
    except ValueError:
        return Response(status=status.HTTP_400_BAD_REQUEST)
    return Response({"received": True})
