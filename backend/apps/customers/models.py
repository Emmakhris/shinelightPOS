from django.conf import settings
from django.db import models

from apps.common.fields import MoneyField


class Customer(models.Model):
    name = models.CharField(max_length=150, db_index=True)
    phone = models.CharField(max_length=30, unique=True, null=True, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    loyalty_points = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credit_limit = MoneyField(help_text="0 means the customer cannot buy on credit.")
    balance = MoneyField(help_text="Amount the customer owes the shop.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class CustomerTransaction(models.Model):
    """Ledger of credit (debt) and loyalty point changes, so balances can always be explained."""

    class Kind(models.TextChoices):
        CREDIT_SALE = "credit_sale", "Bought on credit"
        CREDIT_PAYMENT = "credit_payment", "Paid towards balance"
        CREDIT_REFUND = "credit_refund", "Refund to balance"
        POINTS_EARNED = "points_earned", "Points earned"
        POINTS_REDEEMED = "points_redeemed", "Points redeemed"
        POINTS_REVERSED = "points_reversed", "Points reversed"
        ADJUSTMENT = "adjustment", "Manual adjustment"

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="transactions")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    amount = MoneyField(help_text="Change to balance (positive = customer owes more).")
    points = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    method = models.CharField(max_length=20, blank=True, help_text="How a balance payment was made.")
    reference = models.CharField(max_length=60, blank=True)
    sale = models.ForeignKey("sales.Sale", null=True, blank=True, on_delete=models.SET_NULL)
    shift = models.ForeignKey("shifts.Shift", null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="customer_payments")
    note = models.CharField(max_length=255, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
