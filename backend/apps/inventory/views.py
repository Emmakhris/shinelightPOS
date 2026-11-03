from django.db import transaction
from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from apps.accounts.permissions import HasPerm
from apps.accounts.services import audit
from apps.business.models import Branch
from apps.catalog.models import Variant
from apps.common.csvexport import csv_response, wants_csv
from apps.common.exceptions import BusinessError
from apps.common.money import D

from .models import PurchaseOrder, PurchaseOrderLine, StockLevel, StockMovement, Supplier
from .serializers import (
    AdjustmentSerializer, CountLineSerializer, PurchaseOrderSerializer, StockMovementSerializer,
    SupplierSerializer,
)
from .services import change_stock, set_counted_stock

InventoryPerm = HasPerm("manage_inventory")


@api_view(["GET"])
@permission_classes([HasPerm("manage_inventory", read_perm="sell")])
def stock_levels(request):
    """One row per stock-tracked variant, with value at cost. ?low=1 for items at or below their threshold."""
    branch = Branch.default()
    levels = dict(StockLevel.objects.filter(branch=branch).values_list("variant_id", "quantity"))
    variants = Variant.objects.filter(is_active=True, product__is_active=True, product__track_stock=True)
    search = request.query_params.get("search")
    if search:
        variants = variants.filter(
            Q(product__name__icontains=search) | Q(sku__icontains=search) | Q(barcodes__code=search)
        ).distinct()
    category = request.query_params.get("category")
    if category:
        variants = variants.filter(product__category_id=category)
    rows = []
    for v in variants.select_related("product__category"):
        qty = levels.get(v.pk, D(0))
        low = qty <= v.product.low_stock_threshold
        if request.query_params.get("low") and not low:
            continue
        rows.append({
            "variant": v.pk, "name": v.full_name, "sku": v.sku or "",
            "category": v.product.category.name if v.product.category else "",
            "unit": v.product.unit, "quantity": str(qty), "low_stock_threshold": str(v.product.low_stock_threshold),
            "is_low": low, "cost_price": str(v.cost_price), "price": str(v.price),
            "stock_value": str((qty * v.cost_price).quantize(D("0.01"))),
        })
    rows.sort(key=lambda r: r["name"].lower())
    if wants_csv(request):
        cols = [(k, k) for k in ["name", "sku", "category", "unit", "quantity", "low_stock_threshold",
                                 "cost_price", "price", "stock_value"]]
        return csv_response("stock.csv", cols, rows)
    return Response(rows)


@api_view(["POST"])
@permission_classes([InventoryPerm])
def adjust(request):
    s = AdjustmentSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    variant = get_object_or_404(Variant, pk=s.validated_data["variant"])
    movement = change_stock(
        Branch.default(), variant, s.validated_data["change"], s.validated_data["reason"],
        user=request.user, note=s.validated_data.get("note", ""),
    )
    audit("stock_adjusted", request.user, "variant", variant.pk, change=str(movement.change),
          reason=movement.reason, note=movement.note)
    return Response(StockMovementSerializer(movement).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([InventoryPerm])
def count(request):
    """Submit a stock count: [{variant, counted}, ...]. Only differences are recorded."""
    s = CountLineSerializer(data=request.data.get("lines", []), many=True)
    s.is_valid(raise_exception=True)
    branch = Branch.default()
    note = request.data.get("note") or "Stock count"
    changes = []
    with transaction.atomic():
        for line in s.validated_data:
            variant = get_object_or_404(Variant, pk=line["variant"])
            movement = set_counted_stock(branch, variant, line["counted"], user=request.user, note=note)
            if movement:
                changes.append(StockMovementSerializer(movement).data)
    audit("stock_counted", request.user, lines=len(s.validated_data), changed=len(changes))
    return Response({"changed": changes})


class StockMovementViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = StockMovementSerializer
    permission_classes = [InventoryPerm]
    filterset_fields = {"variant": ["exact"], "reason": ["exact"], "created_at": ["gte", "lte"]}
    search_fields = ["variant__product__name", "reference", "note"]

    def get_queryset(self):
        return StockMovement.objects.select_related("variant__product", "user")


class SupplierViewSet(viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [InventoryPerm]
    search_fields = ["name", "contact_name", "phone"]
    filterset_fields = ["is_active"]


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    serializer_class = PurchaseOrderSerializer
    permission_classes = [InventoryPerm]
    filterset_fields = ["status", "supplier"]
    search_fields = ["number", "supplier__name", "supplier_invoice"]

    def get_queryset(self):
        return PurchaseOrder.objects.select_related("supplier").prefetch_related("lines__variant__product")

    def destroy(self, request, *args, **kwargs):
        order = self.get_object()
        if order.status != PurchaseOrder.Status.DRAFT:
            raise BusinessError("Only draft purchase orders can be deleted. Cancel it instead.")
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def mark_ordered(self, request, pk=None):
        order = self.get_object()
        if order.status != PurchaseOrder.Status.DRAFT:
            raise BusinessError("Only a draft can be marked as ordered.")
        order.status = PurchaseOrder.Status.ORDERED
        order.save(update_fields=["status"])
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()
        if order.status in (PurchaseOrder.Status.RECEIVED, PurchaseOrder.Status.PARTIAL):
            raise BusinessError("Goods have already been received on this order.")
        order.status = PurchaseOrder.Status.CANCELLED
        order.save(update_fields=["status"])
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        """Body: {lines: [{line: id, quantity, unit_cost?}], supplier_invoice?, update_cost?: true}."""
        order = self.get_object()
        if order.status in (PurchaseOrder.Status.RECEIVED, PurchaseOrder.Status.CANCELLED):
            raise BusinessError(f"This order is {order.get_status_display().lower()}.")
        update_cost = request.data.get("update_cost", True)
        with transaction.atomic():
            for entry in request.data.get("lines", []):
                line = order.lines.select_related("variant").filter(pk=entry.get("line")).first()
                qty = D(entry.get("quantity"))
                if not line or qty <= 0:
                    continue
                if entry.get("unit_cost") not in (None, ""):
                    line.unit_cost = D(entry["unit_cost"])
                line.quantity_received = F("quantity_received") + qty
                line.save(update_fields=["quantity_received", "unit_cost"])
                change_stock(order.branch, line.variant, qty, "purchase", user=request.user,
                             reference=order.number, unit_cost=line.unit_cost)
                if update_cost and line.unit_cost:
                    line.variant.cost_price = line.unit_cost
                    line.variant.save(update_fields=["cost_price"])
            if request.data.get("supplier_invoice"):
                order.supplier_invoice = request.data["supplier_invoice"]
            # Query afresh: the prefetched lines still hold the quantities from before this delivery.
            lines = PurchaseOrderLine.objects.filter(order=order)
            fully = all(line.quantity_received >= line.quantity_ordered for line in lines)
            order.status = PurchaseOrder.Status.RECEIVED if fully else PurchaseOrder.Status.PARTIAL
            order.save(update_fields=["status", "supplier_invoice"])
        audit("goods_received", request.user, "purchase_order", order.pk, number=order.number)
        return Response(self.get_serializer(self.get_queryset().get(pk=order.pk)).data)
