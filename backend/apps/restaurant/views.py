from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from apps.accounts.permissions import HasPerm
from apps.accounts.services import audit, require_permission_or_approval
from apps.business.models import Branch
from apps.catalog.models import Variant
from apps.common.exceptions import BusinessError
from apps.common.money import D
from apps.evat import services as evat
from apps.sales import services as sales_services
from apps.sales.models import OrderType
from apps.sales.serializers import CheckoutInput, SaleDetailSerializer

from .models import FloorArea, KitchenTicket, Order, OrderItem, Table
from .serializers import FloorAreaSerializer, KitchenTicketSerializer, OrderSerializer, TableSerializer

TablesPerm = HasPerm("manage_tables", read_perm="sell")


class FloorAreaViewSet(viewsets.ModelViewSet):
    queryset = FloorArea.objects.all()
    serializer_class = FloorAreaSerializer
    permission_classes = [TablesPerm]


class TableViewSet(viewsets.ModelViewSet):
    queryset = Table.objects.select_related("area")
    serializer_class = TableSerializer
    permission_classes = [TablesPerm]
    filterset_fields = ["area", "is_active"]


def _order_qs():
    return Order.objects.select_related("table", "waiter", "customer").prefetch_related("items__variant__product")


@api_view(["GET"])
@permission_classes([HasPerm("sell")])
def floor(request):
    """Areas with their tables and whichever order is open on each table."""
    open_orders = {o.table_id: o for o in _order_qs().filter(status=Order.Status.OPEN, table__isnull=False)}
    areas = []
    for area in FloorArea.objects.prefetch_related("tables"):
        tables = []
        for t in area.tables.all():
            if not t.is_active:
                continue
            order = open_orders.get(t.pk)
            tables.append({
                **TableSerializer(t).data,
                "order": OrderSerializer(order).data if order else None,
            })
        areas.append({**FloorAreaSerializer(area).data, "tables": tables})
    return Response(areas)


class OrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                   viewsets.GenericViewSet):
    serializer_class = OrderSerializer
    permission_classes = [HasPerm("sell")]
    filterset_fields = ["status", "order_type", "table"]

    def get_queryset(self):
        return _order_qs()

    def perform_create(self, serializer):
        table = serializer.validated_data.get("table")
        if table and Order.objects.filter(table=table, status=Order.Status.OPEN).exists():
            raise BusinessError(f"{table.name} already has an open order.")
        order_type = serializer.validated_data.get("order_type") or OrderType.DINE_IN
        if order_type == OrderType.RETAIL:
            raise BusinessError("Choose dine in, takeaway or delivery.")
        with transaction.atomic():
            order = serializer.save(branch=Branch.default(), waiter=self.request.user)
            order.number = f"{order.pk:05d}"
            order.save(update_fields=["number"])

    def _open_order(self):
        order = self.get_object()
        if order.status != Order.Status.OPEN:
            raise BusinessError(f"This order is {order.get_status_display().lower()}.")
        return order

    def _respond(self, order):
        return Response(OrderSerializer(_order_qs().get(pk=order.pk)).data)

    @action(detail=True, methods=["post"])
    def items(self, request, pk=None):
        order = self._open_order()
        variant = get_object_or_404(Variant, pk=request.data.get("variant"), is_active=True)
        qty = D(request.data.get("quantity") or 1)
        if qty <= 0:
            raise BusinessError("Quantity must be above zero.")
        modifiers = [int(m) for m in request.data.get("modifiers") or []]
        # Validate modifiers the same way the till does when the bill is paid.
        from apps.sales.pricing import build_cart_lines

        build_cart_lines([{"variant": variant.pk, "quantity": qty, "modifiers": modifiers}])
        # Same item, same options, not yet sent: just increase the quantity.
        existing = order.items.filter(
            variant=variant, status=OrderItem.Status.PENDING, note=request.data.get("note") or ""
        )
        existing = next((i for i in existing if sorted(i.modifiers) == sorted(modifiers)), None)
        if existing:
            existing.quantity += qty
            existing.save(update_fields=["quantity"])
        else:
            OrderItem.objects.create(order=order, variant=variant, quantity=qty, modifiers=modifiers,
                                     note=request.data.get("note") or "", added_by=request.user)
        return self._respond(order)

    @action(detail=True, methods=["patch", "delete"], url_path=r"items/(?P<item_id>\d+)")
    def item(self, request, pk=None, item_id=None):
        order = self._open_order()
        item = get_object_or_404(order.items, pk=item_id)
        if request.method == "PATCH":
            if item.status != OrderItem.Status.PENDING:
                raise BusinessError("This item was already sent to the kitchen.")
            if "quantity" in request.data:
                qty = D(request.data["quantity"])
                if qty <= 0:
                    item.delete()
                    return self._respond(order)
                item.quantity = qty
            if "note" in request.data:
                item.note = request.data["note"] or ""
            item.save()
            return self._respond(order)
        if item.status == OrderItem.Status.PENDING:
            item.delete()
        elif item.status == OrderItem.Status.SENT:
            approver = require_permission_or_approval(
                request.user, "void", request.data.get("approval_pin"),
                "Removing an item the kitchen already has needs manager approval.",
            )
            item.status = OrderItem.Status.CANCELLED
            item.save(update_fields=["status"])
            audit("order_item_cancelled", request.user, "order", order.pk, approved_by=approver,
                  item=item.variant.full_name, quantity=str(item.quantity))
        return self._respond(order)

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        """Send new items to the kitchen. Returns the kitchen ticket to print (null if nothing for the kitchen)."""
        order = self._open_order()
        with transaction.atomic():
            pending = list(order.items.filter(status=OrderItem.Status.PENDING).select_related("variant__product"))
            if not pending:
                raise BusinessError("There are no new items to send.")
            kitchen = [i for i in pending if i.variant.product.is_kitchen_item]
            ticket = None
            if kitchen:
                ticket = KitchenTicket.objects.create(
                    order=order, number=order.tickets.count() + 1, created_by=request.user
                )
            for i in pending:
                i.status = OrderItem.Status.SENT
                i.ticket = ticket if i in kitchen else None
                i.save(update_fields=["status", "ticket"])
        data = KitchenTicketSerializer(ticket).data if ticket else None
        return Response({"ticket": data, "order": OrderSerializer(_order_qs().get(pk=order.pk)).data})

    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        order = self._open_order()
        table = get_object_or_404(Table, pk=request.data.get("table"), is_active=True)
        if Order.objects.filter(table=table, status=Order.Status.OPEN).exclude(pk=order.pk).exists():
            raise BusinessError(f"{table.name} already has an open order. Merge instead.")
        order.table = table
        order.save(update_fields=["table"])
        return self._respond(order)

    @action(detail=True, methods=["post"])
    def merge(self, request, pk=None):
        """Bring every item from another open order onto this one and close the other order."""
        order = self._open_order()
        other = get_object_or_404(Order, pk=request.data.get("order"), status=Order.Status.OPEN)
        if other.pk == order.pk:
            raise BusinessError("Choose a different order to merge.")
        with transaction.atomic():
            other.items.update(order=order)
            other.tickets.update(order=order)
            order.guests += other.guests
            order.save(update_fields=["guests"])
            other.status = Order.Status.CANCELLED
            other.closed_at = timezone.now()
            other.note = f"Merged into order {order.number}"
            other.save(update_fields=["status", "closed_at", "note"])
        audit("orders_merged", request.user, "order", order.pk, merged=other.number)
        return self._respond(order)

    def _cart_lines(self, order):
        items = [i for i in order.items.all() if i.status != OrderItem.Status.CANCELLED]
        if not items:
            raise BusinessError("The order has no items.")
        return [{"variant": i.variant_id, "quantity": i.quantity, "modifiers": i.modifiers, "note": i.note}
                for i in items]

    @action(detail=True, methods=["post"])
    def bill(self, request, pk=None):
        """Price the order (with optional discount) for the bill printout."""
        order = self._open_order()
        cart = sales_services.quote({
            "lines": self._cart_lines(order),
            "discount_type": request.data.get("discount_type") or "amount",
            "discount_value": D(request.data.get("discount_value")),
        })
        return Response({**cart.as_dict(), "order": OrderSerializer(order).data})

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        order = self._open_order()
        payload = {**request.data, "lines": self._cart_lines(order)}
        if order.customer_id and not payload.get("customer"):
            payload["customer"] = order.customer_id
        s = CheckoutInput(data=payload)
        s.is_valid(raise_exception=True)
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order.pk)
            if order.status != Order.Status.OPEN:
                raise BusinessError("This order was already paid.")
            sale = sales_services.create_sale(
                request.user, s.validated_data, order_type=order.order_type,
                table_name=order.table.name if order.table else (order.customer_label or ""),
            )
            order.items.filter(status=OrderItem.Status.PENDING).update(status=OrderItem.Status.SENT)
            order.status = Order.Status.PAID
            order.sale = sale
            order.closed_at = timezone.now()
            order.save(update_fields=["status", "sale", "closed_at"])
        evat.send_for(sale)
        return Response(SaleDetailSerializer(sale).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self._open_order()
        approver = None
        if order.items.filter(status=OrderItem.Status.SENT).exists():
            approver = require_permission_or_approval(
                request.user, "void", request.data.get("approval_pin"),
                "This order has items the kitchen already has. A manager must approve cancelling it.",
            )
        order.status = Order.Status.CANCELLED
        order.closed_at = timezone.now()
        order.save(update_fields=["status", "closed_at"])
        audit("order_cancelled", request.user, "order", order.pk, approved_by=approver,
              reason=request.data.get("reason", ""))
        return Response(status=status.HTTP_204_NO_CONTENT)


class KitchenTicketViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = KitchenTicketSerializer
    permission_classes = [HasPerm("sell")]
    queryset = KitchenTicket.objects.select_related("order__table", "created_by").prefetch_related(
        "items__variant__product"
    )
