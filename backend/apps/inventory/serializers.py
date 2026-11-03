from django.db import transaction
from rest_framework import serializers

from apps.business.models import Branch

from .models import MANUAL_ADJUSTMENT_REASONS, PurchaseOrder, PurchaseOrderLine, StockMovement, Supplier


class StockMovementSerializer(serializers.ModelSerializer):
    variant_name = serializers.CharField(source="variant.full_name", read_only=True)
    user_name = serializers.CharField(source="user.display_name", read_only=True, default=None)
    reason_label = serializers.CharField(source="get_reason_display", read_only=True)

    class Meta:
        model = StockMovement
        fields = ["id", "created_at", "variant", "variant_name", "change", "quantity_after", "reason",
                  "reason_label", "reference", "unit_cost", "note", "user", "user_name"]


class AdjustmentSerializer(serializers.Serializer):
    variant = serializers.IntegerField()
    change = serializers.DecimalField(max_digits=14, decimal_places=3)
    reason = serializers.ChoiceField(choices=[(r.value, r.label) for r in MANUAL_ADJUSTMENT_REASONS])
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate_change(self, value):
        if value == 0:
            raise serializers.ValidationError("Enter a quantity other than zero.")
        return value


class CountLineSerializer(serializers.Serializer):
    variant = serializers.IntegerField()
    counted = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=0)


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = "__all__"


class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    variant_name = serializers.CharField(source="variant.full_name", read_only=True)

    class Meta:
        model = PurchaseOrderLine
        fields = ["id", "variant", "variant_name", "quantity_ordered", "quantity_received", "unit_cost"]
        read_only_fields = ["quantity_received"]


class PurchaseOrderSerializer(serializers.ModelSerializer):
    lines = PurchaseOrderLineSerializer(many=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrder
        fields = ["id", "number", "supplier", "supplier_name", "status", "expected_date", "supplier_invoice",
                  "notes", "created_at", "lines", "total"]
        read_only_fields = ["number", "status", "created_at"]

    def get_total(self, obj):
        return str(sum((line.quantity_ordered * line.unit_cost for line in obj.lines.all()), 0))

    def validate_lines(self, lines):
        if not lines:
            raise serializers.ValidationError("Add at least one item.")
        return lines

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("lines")
        last = PurchaseOrder.objects.order_by("-pk").first()
        number = f"PO-{(last.pk + 1 if last else 1):06d}"
        order = PurchaseOrder.objects.create(
            number=number, branch=Branch.default(), created_by=self.context["request"].user, **validated_data
        )
        for line in lines:
            line.pop("id", None)
            PurchaseOrderLine.objects.create(order=order, **line)
        return order

    @transaction.atomic
    def update(self, instance, validated_data):
        if instance.status not in (PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.ORDERED):
            raise serializers.ValidationError("Only draft or ordered purchase orders can be edited.")
        lines = validated_data.pop("lines", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        if lines is not None:
            instance.lines.all().delete()
            for line in lines:
                line.pop("id", None)
                PurchaseOrderLine.objects.create(order=instance, **line)
        return instance
