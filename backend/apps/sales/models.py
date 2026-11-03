from django.conf import settings
from django.db import models

from apps.common.fields import MoneyField, QtyField


class PaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    MOMO = "momo", "Mobile Money"
    CARD = "card", "Card"
    BANK = "bank", "Bank transfer"
    CREDIT = "credit", "Customer credit"
    POINTS = "points", "Loyalty points"


class MomoNetwork(models.TextChoices):
    MTN = "mtn", "MTN MoMo"
    TELECEL = "telecel", "Telecel Cash"
    AT = "at", "AT Money"


class OrderType(models.TextChoices):
    RETAIL = "retail", "Retail"
    DINE_IN = "dine_in", "Dine in"
    TAKEAWAY = "takeaway", "Takeaway"
    DELIVERY = "delivery", "Delivery"


class Sale(models.Model):
    """A completed sale. Never edited after creation: mistakes are fixed with a refund or a void."""

    class Status(models.TextChoices):
        COMPLETED = "completed", "Completed"
        PARTIALLY_REFUNDED = "partially_refunded", "Partly refunded"
        REFUNDED = "refunded", "Refunded"
        VOIDED = "voided", "Voided"

    branch = models.ForeignKey("business.Branch", on_delete=models.PROTECT)
    invoice_number = models.CharField(max_length=40, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.COMPLETED, db_index=True)
    order_type = models.CharField(max_length=10, choices=OrderType.choices, default=OrderType.RETAIL)
    table_name = models.CharField(max_length=50, blank=True)
    customer = models.ForeignKey("customers.Customer", null=True, blank=True, on_delete=models.PROTECT,
                                 related_name="sales")
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sales")
    shift = models.ForeignKey("shifts.Shift", null=True, blank=True, on_delete=models.PROTECT, related_name="sales")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    prices_include_tax = models.BooleanField(default=True)
    subtotal = MoneyField(help_text="Sum of list prices x quantity, before discounts.")
    discount_total = MoneyField()
    tax_total = MoneyField()
    total = MoneyField(help_text="Amount the customer pays.")
    paid_total = MoneyField()
    change_due = MoneyField()
    cost_total = MoneyField()
    points_earned = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    points_redeemed = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    note = models.CharField(max_length=255, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+", help_text="Manager who approved a discount or price change.")

    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="+")
    void_reason = models.CharField(max_length=255, blank=True)

    # Filled by the GRA E-VAT integration (Phase 2).
    evat_status = models.CharField(max_length=20, blank=True)
    evat_reference = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return self.invoice_number


class SaleLine(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="lines")
    variant = models.ForeignKey("catalog.Variant", on_delete=models.PROTECT)
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=60, blank=True)
    quantity = QtyField()
    unit_price = MoneyField(help_text="Price per unit including modifiers, before discount.")
    modifiers = models.JSONField(default=list, blank=True)
    discount = MoneyField()
    net_amount = MoneyField(help_text="Line value excluding tax, after discounts.")
    tax_amount = MoneyField()
    total = MoneyField(help_text="Line value including tax, after discounts.")
    unit_cost = MoneyField()
    tax_category = models.CharField(max_length=10)
    track_stock = models.BooleanField(default=True)
    refunded_quantity = QtyField()
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["pk"]


class SaleTax(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="taxes")
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=50)
    rate = models.DecimalField(max_digits=6, decimal_places=3)
    amount = MoneyField()


class Payment(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="payments")
    method = models.CharField(max_length=10, choices=PaymentMethod.choices)
    amount = MoneyField()
    momo_network = models.CharField(max_length=10, choices=MomoNetwork.choices, blank=True)
    reference = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Refund(models.Model):
    number = models.CharField(max_length=40, unique=True)
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="refunds")
    shift = models.ForeignKey("shifts.Shift", null=True, blank=True, on_delete=models.PROTECT, related_name="refunds")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    method = models.CharField(max_length=10, choices=PaymentMethod.choices)
    reference = models.CharField(max_length=100, blank=True)
    amount = MoneyField()
    tax_amount = MoneyField()
    reason = models.CharField(max_length=255)
    restocked = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class RefundLine(models.Model):
    refund = models.ForeignKey(Refund, on_delete=models.CASCADE, related_name="lines")
    sale_line = models.ForeignKey(SaleLine, on_delete=models.PROTECT, related_name="refund_lines")
    quantity = QtyField()
    amount = MoneyField()
    tax_amount = MoneyField()


class HeldSale(models.Model):
    """A parked cart. Stored on the server so it can be recalled from any till."""

    label = models.CharField(max_length=100, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    customer = models.ForeignKey("customers.Customer", null=True, blank=True, on_delete=models.SET_NULL)
    cart = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
