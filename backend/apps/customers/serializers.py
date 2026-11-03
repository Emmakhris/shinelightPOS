from decimal import Decimal

from rest_framework import serializers

from .models import Customer, CustomerTransaction


class CustomerSerializer(serializers.ModelSerializer):
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = Customer
        fields = ["id", "name", "phone", "email", "address", "notes", "loyalty_points", "credit_limit",
                  "balance", "is_active", "created_at"]
        read_only_fields = ["loyalty_points", "balance", "created_at"]

    def validate_phone(self, value):
        value = (value or "").strip() or None
        if value and Customer.objects.filter(phone=value).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise serializers.ValidationError("Another customer already has this phone number.")
        return value


class CustomerTransactionSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    invoice_number = serializers.CharField(source="sale.invoice_number", read_only=True, default=None)
    user_name = serializers.CharField(source="user.display_name", read_only=True, default=None)

    class Meta:
        model = CustomerTransaction
        fields = ["id", "created_at", "kind", "kind_label", "amount", "points", "method", "reference",
                  "sale", "invoice_number", "note", "user_name"]


class BalancePaymentSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    method = serializers.ChoiceField(choices=["cash", "momo", "card", "bank"])
    reference = serializers.CharField(required=False, allow_blank=True, max_length=60)
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)
