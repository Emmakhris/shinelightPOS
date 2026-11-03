from django.conf import settings
from django.db import models

from apps.common.fields import MoneyField


class Shift(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    branch = models.ForeignKey("business.Branch", on_delete=models.PROTECT)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="shifts")
    register_name = models.CharField(max_length=50, default="Till 1")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    opening_float = MoneyField()
    expected_cash = MoneyField(null=True, blank=True, default=None)
    counted_cash = MoneyField(null=True, blank=True, default=None)
    difference = MoneyField(null=True, blank=True, default=None)
    closing_note = models.TextField(blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    report = models.JSONField(null=True, blank=True, help_text="Z report snapshot taken at close.")

    class Meta:
        ordering = ["-opened_at"]
        constraints = [
            models.UniqueConstraint(fields=["user"], condition=models.Q(status="open"), name="one_open_shift_per_user")
        ]

    def __str__(self):
        return f"{self.user} {self.opened_at:%Y-%m-%d %H:%M}"


class CashMovement(models.Model):
    class Kind(models.TextChoices):
        PAID_IN = "paid_in", "Cash in"
        PAID_OUT = "paid_out", "Cash out"
        DROP = "drop", "Cash drop to safe"

    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name="cash_movements")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    amount = MoneyField()
    reason = models.CharField(max_length=200)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
