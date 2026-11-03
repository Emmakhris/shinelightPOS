from rest_framework import serializers

from .models import Branch, BusinessProfile, Expense, TaxRate


class BusinessProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessProfile
        exclude = ["id"]
        read_only_fields = ["setup_complete", "updated_at"]


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = "__all__"
        read_only_fields = ["next_invoice_number", "next_refund_number"]


class TaxRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxRate
        fields = "__all__"


class ExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = "__all__"


class SetupSerializer(serializers.Serializer):
    business_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=50, required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    tin = serializers.CharField(max_length=50, required=False, allow_blank=True)
    vat_registered = serializers.BooleanField(default=False)
    retail_mode = serializers.BooleanField(default=True)
    restaurant_mode = serializers.BooleanField(default=False)
    prices_include_tax = serializers.BooleanField(default=True)
    owner_first_name = serializers.CharField(max_length=150)
    owner_last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    owner_username = serializers.CharField(max_length=150)
    owner_password = serializers.CharField(min_length=6)
    owner_pin = serializers.RegexField(r"^\d{4,6}$")
    demo_data = serializers.BooleanField(default=False)

    def validate(self, attrs):
        if not (attrs["retail_mode"] or attrs["restaurant_mode"]):
            raise serializers.ValidationError("Turn on retail mode, restaurant mode or both.")
        return attrs
