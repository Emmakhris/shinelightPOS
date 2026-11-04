from django.db import models


class EvatSubmission(models.Model):
    """
    One document reported to GRA E-VAT. It is saved with the sale, refund or void and sent after
    the database commits, so a sale never waits on GRA or fails because GRA cannot be reached.
    """

    class Kind(models.TextChoices):
        INVOICE = "invoice", "Invoice"
        REFUND = "refund", "Refund"
        VOID = "void", "Void"

    class Status(models.TextChoices):
        PENDING = "pending", "Not sent yet"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    number = models.CharField(max_length=60, unique=True, help_text="Invoice or refund number.")
    sale = models.ForeignKey("sales.Sale", on_delete=models.PROTECT, related_name="evat_submissions")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    simulated = models.BooleanField(default=False, help_text="Answered by the simulator. Nothing went to GRA.")
    payload = models.JSONField()
    reference = models.CharField(max_length=100, blank=True)
    message = models.CharField(max_length=255, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "pk"]

    def __str__(self):
        return f"{self.number} {self.status}"
