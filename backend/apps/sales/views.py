from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from apps.accounts.permissions import HasPerm
from apps.common.csvexport import csv_response, wants_csv

from . import services
from apps.evat import services as evat
from apps.payments import paystack

from .models import HeldSale, Refund, Sale
from .serializers import (
    CheckoutInput, HeldSaleSerializer, QuoteInput, RefundInput, RefundSerializer, SaleDetailSerializer,
    SaleListSerializer,
)


@api_view(["POST"])
@permission_classes([HasPerm("sell")])
def quote(request):
    s = QuoteInput(data=request.data)
    s.is_valid(raise_exception=True)
    return Response(services.quote(s.validated_data).as_dict())


@api_view(["POST"])
@permission_classes([HasPerm("sell")])
def checkout(request):
    s = CheckoutInput(data=request.data)
    s.is_valid(raise_exception=True)
    sale = services.create_sale(request.user, s.validated_data)
    evat.send_for(sale)
    return Response(SaleDetailSerializer(sale).data, status=status.HTTP_201_CREATED)


class SaleViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [HasPerm("sell")]
    filterset_fields = {
        "created_at": ["gte", "lte"], "status": ["exact"], "cashier": ["exact"], "customer": ["exact"],
        "order_type": ["exact"], "payments__method": ["exact"],
    }
    search_fields = ["invoice_number", "customer__name", "customer__phone", "payments__reference"]
    ordering_fields = ["created_at", "total"]

    def get_queryset(self):
        qs = Sale.objects.select_related("cashier", "customer").prefetch_related("payments").distinct()
        user = self.request.user
        if not user.has_pos_perm("view_reports"):
            qs = qs.filter(cashier=user)  # cashiers only see their own sales
        if self.action == "retrieve":
            qs = qs.prefetch_related("lines", "taxes", "refunds__lines__sale_line", "refunds__user")
        return qs

    def get_serializer_class(self):
        return SaleDetailSerializer if self.action == "retrieve" else SaleListSerializer

    def list(self, request, *args, **kwargs):
        if wants_csv(request):
            qs = self.filter_queryset(self.get_queryset())[:20000]
            rows = [{
                "invoice": s.invoice_number, "date": s.created_at.strftime("%Y-%m-%d %H:%M"),
                "status": s.status, "type": s.order_type, "cashier": s.cashier.display_name,
                "customer": s.customer.name if s.customer else "", "subtotal": s.subtotal,
                "discount": s.discount_total, "tax": s.tax_total, "total": s.total,
                "payments": " + ".join(f"{p.method} {p.amount}" for p in s.payments.all()),
            } for s in qs]
            return csv_response("sales.csv", [(k, k) for k in rows[0]] if rows else [("invoice", "invoice")], rows)
        return super().list(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def refund(self, request, pk=None):
        sale = self.get_object()
        s = RefundInput(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        refund = services.create_refund(
            request.user, sale, d["lines"], d["method"], d["reason"], d["restock"], d.get("approval_pin"),
            d.get("reference", ""), d["through_paystack"],
        )
        if d["through_paystack"]:
            # The refund is committed, so the wallet is only paid for a refund that is on record.
            paystack.send_refund(refund.paystack_refund)
        evat.send_for(sale)
        return Response(RefundSerializer(refund).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        sale = self.get_object()
        services.void_sale(request.user, sale, request.data.get("reason", ""), request.data.get("approval_pin"))
        evat.send_for(sale)
        return Response(SaleDetailSerializer(Sale.objects.get(pk=sale.pk)).data)


class RefundViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = RefundSerializer
    permission_classes = [HasPerm("view_reports")]
    filterset_fields = {"created_at": ["gte", "lte"], "method": ["exact"]}
    search_fields = ["number", "sale__invoice_number"]

    def get_queryset(self):
        return Refund.objects.select_related("sale", "user", "approved_by").prefetch_related("lines__sale_line")


class HeldSaleViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.DestroyModelMixin,
                      viewsets.GenericViewSet):
    serializer_class = HeldSaleSerializer
    permission_classes = [HasPerm("sell")]
    queryset = HeldSale.objects.select_related("user", "customer")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
