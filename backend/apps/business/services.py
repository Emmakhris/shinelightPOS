from django.db import transaction

from .models import Branch


def next_document_number(branch, kind="invoice"):
    """Sequential, gap-free numbers per branch. Must be called inside the sale/refund transaction."""
    with transaction.atomic():
        locked = Branch.objects.select_for_update().get(pk=branch.pk)
        if kind == "invoice":
            number = locked.next_invoice_number
            locked.next_invoice_number += 1
            locked.save(update_fields=["next_invoice_number"])
            return f"{locked.invoice_prefix}-{locked.code}-{number:06d}"
        number = locked.next_refund_number
        locked.next_refund_number += 1
        locked.save(update_fields=["next_refund_number"])
        return f"RF-{locked.code}-{number:06d}"
