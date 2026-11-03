from rest_framework import serializers

from .models import HeldSale, MomoNetwork, Payment, PaymentMethod, Refund, RefundLine, Sale, SaleLine, SaleTax

DISCOUNT_TYPES = ["amount", "percent"]


class CartLineInput(serializers.Serializer):
    variant = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)
    modifiers = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
    discount_type = serializers.ChoiceField(choices=DISCOUNT_TYPES, required=False, default="amount")
    discount_value = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, default=0)
    unit_price = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, default="")


class PaymentInput(serializers.Serializer):
    method = serializers.ChoiceField(choices=PaymentMethod.choices)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    momo_network = serializers.ChoiceField(choices=MomoNetwork.choices, required=False, allow_blank=True)
    reference = serializers.CharField(required=False, allow_blank=True, max_length=100)


class QuoteInput(serializers.Serializer):
    lines = CartLineInput(many=True)
    discount_type = serializers.ChoiceField(choices=DISCOUNT_TYPES, required=False, default="amount")
    discount_value = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, default=0)


class CheckoutInput(QuoteInput):
    payments = PaymentInput(many=True)
    customer = serializers.IntegerField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)
    approval_pin = serializers.CharField(required=False, allow_blank=True)


class RefundInput(serializers.Serializer):
    lines = serializers.ListField(child=serializers.DictField())
    method = serializers.ChoiceField(choices=PaymentMethod.choices)
    reason = serializers.CharField(max_length=255)
    restock = serializers.BooleanField(default=True)
    reference = serializers.CharField(required=False, allow_blank=True, max_length=100)
    approval_pin = serializers.CharField(required=False, allow_blank=True)


class SaleLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleLine
        fields = ["id", "variant", "name", "sku", "quantity", "unit_price", "modifiers", "discount", "net_amount",
                  "tax_amount", "total", "tax_category", "refunded_quantity", "note"]


class SaleTaxSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleTax
        fields = ["code", "name", "rate", "amount"]


class PaymentSerializer(serializers.ModelSerializer):
    method_label = serializers.CharField(source="get_method_display", read_only=True)

    class Meta:
        model = Payment
        fields = ["id", "method", "method_label", "amount", "momo_network", "reference"]


class RefundLineSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="sale_line.name", read_only=True)

    class Meta:
        model = RefundLine
        fields = ["sale_line", "name", "quantity", "amount", "tax_amount"]


class RefundSerializer(serializers.ModelSerializer):
    lines = RefundLineSerializer(many=True, read_only=True)
    user_name = serializers.CharField(source="user.display_name", read_only=True)
    approved_by_name = serializers.CharField(source="approved_by.display_name", read_only=True, default=None)
    invoice_number = serializers.CharField(source="sale.invoice_number", read_only=True)

    class Meta:
        model = Refund
        fields = ["id", "number", "sale", "invoice_number", "method", "reference", "amount", "tax_amount", "reason",
                  "restocked", "created_at", "user_name", "approved_by_name", "lines"]


class SaleListSerializer(serializers.ModelSerializer):
    cashier_name = serializers.CharField(source="cashier.display_name", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True, default=None)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    payment_methods = serializers.SerializerMethodField()

    class Meta:
        model = Sale
        fields = ["id", "invoice_number", "created_at", "status", "status_label", "order_type", "table_name",
                  "cashier_name", "customer", "customer_name", "total", "payment_methods"]

    def get_payment_methods(self, obj):
        return sorted({p.method for p in obj.payments.all()})


class SaleDetailSerializer(SaleListSerializer):
    lines = SaleLineSerializer(many=True, read_only=True)
    taxes = SaleTaxSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    refunds = RefundSerializer(many=True, read_only=True)
    approved_by_name = serializers.CharField(source="approved_by.display_name", read_only=True, default=None)
    voided_by_name = serializers.CharField(source="voided_by.display_name", read_only=True, default=None)
    customer_phone = serializers.CharField(source="customer.phone", read_only=True, default=None)

    class Meta(SaleListSerializer.Meta):
        fields = SaleListSerializer.Meta.fields + [
            "prices_include_tax", "subtotal", "discount_total", "tax_total", "paid_total", "change_due",
            "cost_total", "points_earned", "points_redeemed", "note", "approved_by_name", "voided_at",
            "voided_by_name", "void_reason", "customer_phone", "lines", "taxes", "payments", "refunds",
            "evat_status", "evat_reference",
        ]


class HeldSaleSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.display_name", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True, default=None)

    class Meta:
        model = HeldSale
        fields = ["id", "label", "user_name", "customer", "customer_name", "cart", "created_at"]
