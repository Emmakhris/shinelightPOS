from django.conf import settings
from django.db import models

from apps.common.fields import MoneyField, QtyField


class StockLevel(models.Model):
    branch = models.ForeignKey("business.Branch", on_delete=models.CASCADE, related_name="stock_levels")
    variant = models.ForeignKey("catalog.Variant", on_delete=models.CASCADE, related_name="stock_levels")
    quantity = QtyField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["branch", "variant"], name="unique_stock_per_branch")]

    def __str__(self):
        return f"{self.variant} @ {self.branch}: {self.quantity}"


class MovementReason(models.TextChoices):
    OPENING = "opening", "Opening stock"
    SALE = "sale", "Sale"
    REFUND = "refund", "Refund / return"
    VOID = "void", "Voided sale"
    PURCHASE = "purchase", "Goods received"
    COUNT = "count", "Stock count"
    DAMAGE = "damage", "Damaged"
    THEFT = "theft", "Theft / loss"
    EXPIRED = "expired", "Expired"
    INTERNAL_USE = "internal_use", "Internal use"
    CORRECTION = "correction", "Correction"
    TRANSFER_IN = "transfer_in", "Transfer in"
    TRANSFER_OUT = "transfer_out", "Transfer out"


MANUAL_ADJUSTMENT_REASONS = [
    MovementReason.DAMAGE, MovementReason.THEFT, MovementReason.EXPIRED,
    MovementReason.INTERNAL_USE, MovementReason.CORRECTION, MovementReason.OPENING,
]


class StockMovement(models.Model):
    """Append-only ledger. StockLevel.quantity always equals the sum of a variant's movements."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    branch = models.ForeignKey("business.Branch", on_delete=models.PROTECT)
    variant = models.ForeignKey("catalog.Variant", on_delete=models.PROTECT, related_name="movements")
    change = QtyField()
    quantity_after = QtyField()
    reason = models.CharField(max_length=20, choices=MovementReason.choices)
    reference = models.CharField(max_length=60, blank=True)
    unit_cost = MoneyField()
    note = models.CharField(max_length=255, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-created_at", "-pk"]


class Supplier(models.Model):
    name = models.CharField(max_length=150)
    contact_name = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ORDERED = "ordered", "Ordered"
        PARTIAL = "partial", "Partly received"
        RECEIVED = "received", "Received"
        CANCELLED = "cancelled", "Cancelled"

    number = models.CharField(max_length=30, unique=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_orders")
    branch = models.ForeignKey("business.Branch", on_delete=models.PROTECT)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    expected_date = models.DateField(null=True, blank=True)
    supplier_invoice = models.CharField(max_length=60, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.number


class PurchaseOrderLine(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    variant = models.ForeignKey("catalog.Variant", on_delete=models.PROTECT)
    quantity_ordered = QtyField()
    quantity_received = QtyField()
    unit_cost = MoneyField()
