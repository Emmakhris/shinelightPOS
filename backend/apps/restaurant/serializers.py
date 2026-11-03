from rest_framework import serializers

from apps.catalog.models import Modifier
from apps.common.money import ZERO, money

from .models import FloorArea, KitchenTicket, Order, OrderItem, Table


class TableSerializer(serializers.ModelSerializer):
    class Meta:
        model = Table
        fields = ["id", "area", "name", "seats", "sort_order", "is_active"]


class FloorAreaSerializer(serializers.ModelSerializer):
    class Meta:
        model = FloorArea
        fields = ["id", "name", "sort_order"]


def _modifier_lookup(items):
    ids = {m for item in items for m in item.modifiers}
    return {m.pk: m for m in Modifier.objects.filter(pk__in=ids)}


class OrderItemSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="variant.full_name", read_only=True)
    modifier_details = serializers.SerializerMethodField()
    unit_price = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    is_kitchen_item = serializers.BooleanField(source="variant.product.is_kitchen_item", read_only=True)

    class Meta:
        model = OrderItem
        fields = ["id", "variant", "name", "quantity", "modifiers", "modifier_details", "unit_price", "note",
                  "status", "status_label", "is_kitchen_item", "created_at"]
        read_only_fields = ["status"]

    def _mods(self, obj):
        lookup = self.context.get("modifiers")
        if lookup is None:
            lookup = _modifier_lookup([obj])
        return [lookup[m] for m in obj.modifiers if m in lookup]

    def get_modifier_details(self, obj):
        return [{"id": m.pk, "name": m.name, "price": str(m.price)} for m in self._mods(obj)]

    def get_unit_price(self, obj):
        return str(obj.variant.price + sum((m.price for m in self._mods(obj)), ZERO))


class OrderSerializer(serializers.ModelSerializer):
    table_name = serializers.CharField(source="table.name", read_only=True, default=None)
    waiter_name = serializers.CharField(source="waiter.display_name", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True, default=None)
    items = serializers.SerializerMethodField()
    estimated_total = serializers.SerializerMethodField()
    pending_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ["id", "number", "table", "table_name", "order_type", "status", "waiter_name", "customer",
                  "customer_name", "customer_label", "guests", "note", "created_at", "items", "estimated_total",
                  "pending_count", "sale"]
        read_only_fields = ["number", "status", "sale"]

    def _live_items(self, obj):
        return [i for i in obj.items.all() if i.status != OrderItem.Status.CANCELLED]

    def get_items(self, obj):
        items = list(obj.items.all())
        ctx = {**self.context, "modifiers": _modifier_lookup(items)}
        return OrderItemSerializer(items, many=True, context=ctx).data

    def get_estimated_total(self, obj):
        items = self._live_items(obj)
        mods = _modifier_lookup(items)
        total = sum(
            ((i.variant.price + sum((mods[m].price for m in i.modifiers if m in mods), ZERO)) * i.quantity
             for i in items), ZERO,
        )
        return str(money(total))

    def get_pending_count(self, obj):
        return sum(1 for i in obj.items.all() if i.status == OrderItem.Status.PENDING)


class KitchenTicketSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    order_number = serializers.CharField(source="order.number", read_only=True)
    table_name = serializers.CharField(source="order.table.name", read_only=True, default=None)
    order_type = serializers.CharField(source="order.order_type", read_only=True)
    waiter_name = serializers.CharField(source="created_by.display_name", read_only=True, default=None)

    class Meta:
        model = KitchenTicket
        fields = ["id", "number", "order", "order_number", "table_name", "order_type", "waiter_name",
                  "created_at", "items"]
