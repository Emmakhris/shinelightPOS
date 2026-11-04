from django.conf import settings
from django.db import models

from apps.common.fields import MoneyField
from apps.common.money import ZERO

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

    @property
    def refundable_amount(self):
        """Failed refunds still count: they stay owed to the customer until retried or paid by hand."""
        if self.status != self.Status.SUCCESS:
            return ZERO
        return self.amount - sum((r.amount for r in self.refunds.all()), ZERO)


class PaystackRefund(models.Model):
    """
    Money going back to the customer's MoMo wallet through Paystack, for a sale refund or for a
    charge that never reached a sale. The row is saved first and sent after the database commit,
    so a crash or lost connection leaves a visible "not sent" row that can be sent again safely.
    """

    class Status(models.TextChoices):
        SENDING = "sending", "Not sent yet"
        PENDING = "pending", "Waiting on Paystack"
        PROCESSING = "processing", "Being processed"
        NEEDS_ATTENTION = "needs-attention", "Needs attention"
        PROCESSED = "processed", "Sent back"
        FAILED = "failed", "Failed"
        SETTLED = "settled", "Paid by hand"

    reference = models.CharField(max_length=64, unique=True)
    charge = models.ForeignKey(PaystackCharge, on_delete=models.PROTECT, related_name="refunds")
    sale_refund = models.OneToOneField(
        "sales.Refund", null=True, blank=True, on_delete=models.SET_NULL, related_name="paystack_refund"
    )
    amount = MoneyField()
    reason = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SENDING, db_index=True)
    message = models.CharField(max_length=255, blank=True, help_text="Paystack's reason, or the note when paid by hand.")
    raw = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} {self.amount} {self.status}"
