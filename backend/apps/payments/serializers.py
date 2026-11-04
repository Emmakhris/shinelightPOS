from rest_framework import serializers

from .models import PaystackRefund


class PaystackRefundSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    phone = serializers.CharField(source="charge.phone", read_only=True)
    network = serializers.CharField(source="charge.network", read_only=True)
    charge_reference = serializers.CharField(source="charge.reference", read_only=True)
    refund_number = serializers.CharField(source="sale_refund.number", read_only=True, default=None)
    invoice_number = serializers.CharField(source="sale_refund.sale.invoice_number", read_only=True, default=None)
    sale = serializers.IntegerField(source="sale_refund.sale_id", read_only=True, default=None)
    created_by_name = serializers.CharField(source="created_by.display_name", read_only=True, default=None)

    class Meta:
        model = PaystackRefund
        fields = ["reference", "amount", "reason", "status", "status_label", "message", "phone", "network",
                  "charge_reference", "refund_number", "invoice_number", "sale", "created_at", "created_by_name"]
