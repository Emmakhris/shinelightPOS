from django.conf import settings
from django.db import models

from apps.common.fields import QtyField
from apps.sales.models import OrderType


class FloorArea(models.Model):
    name = models.CharField(max_length=60)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class Table(models.Model):
    area = models.ForeignKey(FloorArea, on_delete=models.CASCADE, related_name="tables")
    name = models.CharField(max_length=30)
    seats = models.PositiveSmallIntegerField(default=4)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["area__sort_order", "sort_order", "name"]

    def __str__(self):
        return self.name


class Order(models.Model):
    """An open tab: items are added over time, sent to the kitchen, then paid as one sale."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    number = models.CharField(max_length=20, blank=True)
    branch = models.ForeignKey("business.Branch", on_delete=models.PROTECT)
    table = models.ForeignKey(Table, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    order_type = models.CharField(max_length=10, choices=OrderType.choices, default=OrderType.DINE_IN)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True)
    waiter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    customer = models.ForeignKey("customers.Customer", null=True, blank=True, on_delete=models.SET_NULL)
    customer_label = models.CharField(max_length=100, blank=True, help_text="Name / phone for takeaway or delivery.")
    guests = models.PositiveSmallIntegerField(default=1)
    note = models.CharField(max_length=255, blank=True)
    sale = models.OneToOneField("sales.Sale", null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="restaurant_order")
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.number


class KitchenTicket(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="tickets")
    number = models.PositiveSmallIntegerField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class OrderItem(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Not sent"
        SENT = "sent", "Sent to kitchen"
        CANCELLED = "cancelled", "Cancelled"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey("catalog.Variant", on_delete=models.PROTECT)
    quantity = QtyField(default=1)
    modifiers = models.JSONField(default=list, blank=True, help_text="Modifier ids.")
    note = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    ticket = models.ForeignKey(KitchenTicket, null=True, blank=True, on_delete=models.SET_NULL, related_name="items")
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
