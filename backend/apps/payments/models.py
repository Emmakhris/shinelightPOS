from django.conf import settings
from django.db import models

from apps.common.fields import MoneyField

# Our network names (as used on sales.Payment.momo_network) -> Paystack provider codes.
PAYSTACK_PROVIDERS = {"mtn": "mtn", "telecel": "vod", "at": "atl"}


class PaystackCharge(models.Model):
    """
    One mobile money prompt sent through Paystack. A successful charge is attached to
    exactly one sale payment; until then it shows as unmatched for reconciliation.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Sending"
        PAY_OFFLINE = "pay_offline", "Waiting for customer"
        SEND_OTP = "send_otp", "Needs code from customer"
        SUCCESS = "success", "Paid"
        FAILED = "failed", "Failed"
        ABANDONED = "abandoned", "Cancelled at till"

    reference = models.CharField(max_length=60, unique=True)
    amount = MoneyField()
    currency = models.CharField(max_length=3, default="GHS")
    phone = models.CharField(max_length=20)
    network = models.CharField(max_length=10)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    display_text = models.CharField(max_length=255, blank=True)
    message = models.CharField(max_length=255, blank=True, help_text="Paystack's reason, e.g. why it failed.")
    paystack_id = models.CharField(max_length=40, blank=True)
    raw = models.JSONField(default=dict, blank=True)
    payment = models.OneToOneField(
        "sales.Payment", null=True, blank=True, on_delete=models.SET_NULL, related_name="paystack_charge"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} {self.amount} {self.status}"

    @property
    def is_final(self):
        return self.status in (self.Status.SUCCESS, self.Status.FAILED)
