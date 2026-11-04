from django.utils import timezone

from apps.business.models import BusinessProfile

from . import connector
from .models import EvatSubmission

Kind = EvatSubmission.Kind
Status = EvatSubmission.Status


def _base_payload(kind, number, sale, issued_at):
    profile = BusinessProfile.get()
    return {
        "kind": kind,
        "number": number,
        "invoice": sale.invoice_number,
        "issued_at": issued_at.isoformat(),
        "seller": {"name": profile.legal_name or profile.name, "tin": profile.tin},
        "customer": {"name": sale.customer.name, "phone": sale.customer.phone} if sale.customer else None,
        "cashier": sale.cashier.display_name,
        "currency": profile.currency_code or "GHS",
        "prices_include_tax": sale.prices_include_tax,
    }


def _sale_payload(kind, number, sale, issued_at):
    return {
        **_base_payload(kind, number, sale, issued_at),
        "lines": [{
            "name": sl.name, "sku": sl.sku, "quantity": str(sl.quantity), "unit_price": str(sl.unit_price),
            "discount": str(sl.discount), "net": str(sl.net_amount), "tax": str(sl.tax_amount),
            "total": str(sl.total), "tax_category": sl.tax_category,
        } for sl in sale.lines.all()],
        "taxes": [{"code": t.code, "name": t.name, "rate": str(t.rate), "amount": str(t.amount)}
                  for t in sale.taxes.all()],
        "discount_total": str(sale.discount_total),
        "tax_total": str(sale.tax_total),
        "total": str(sale.total),
    }


def queue_invoice(sale):
    """Called inside the sale's transaction. Does nothing unless E-VAT is switched on."""
    if not BusinessProfile.get().evat_enabled:
        return None
    sale.evat_status = Status.PENDING
    sale.save(update_fields=["evat_status"])
    return EvatSubmission.objects.create(
        kind=Kind.INVOICE, number=sale.invoice_number, sale=sale,
        payload=_sale_payload(Kind.INVOICE, sale.invoice_number, sale, sale.created_at),
    )


def _was_reported(sale):
    # A sale made before E-VAT was switched on has nothing at GRA to correct.
    return sale.evat_submissions.filter(kind=Kind.INVOICE).exists()


def queue_refund(refund):
    if not _was_reported(refund.sale):
        return None
    payload = {
        **_base_payload(Kind.REFUND, refund.number, refund.sale, refund.created_at),
        "lines": [{"name": rl.sale_line.name, "quantity": str(rl.quantity), "total": str(rl.amount),
                   "tax": str(rl.tax_amount)} for rl in refund.lines.select_related("sale_line")],
        "tax_total": str(refund.tax_amount),
        "total": str(refund.amount),
        "reason": refund.reason,
    }
    return EvatSubmission.objects.create(kind=Kind.REFUND, number=refund.number, sale=refund.sale, payload=payload)


def queue_void(sale):
    if not _was_reported(sale):
        return None
    number = f"{sale.invoice_number}-VOID"
    payload = {**_sale_payload(Kind.VOID, number, sale, sale.voided_at), "reason": sale.void_reason}
    return EvatSubmission.objects.create(kind=Kind.VOID, number=number, sale=sale, payload=payload)


def _send(sub):
    sub.attempts += 1
    try:
        result = connector.submit(sub.payload)
    except connector.EvatUnavailable as exc:
        sub.message = str(exc)[:255] or "Could not reach GRA."
        sub.save(update_fields=["attempts", "message"])
        return False
    sub.status = Status.ACCEPTED if result["accepted"] else Status.REJECTED
    sub.reference = result.get("reference", "")[:100]
    sub.message = result.get("message", "")[:255]
    sub.simulated = connector.mode() == "simulated"
    sub.sent_at = timezone.now()
    sub.save()
    if sub.kind == Kind.INVOICE:
        type(sub.sale).objects.filter(pk=sub.sale_id).update(evat_status=sub.status, evat_reference=sub.reference)
    return sub.status == Status.ACCEPTED


def _send_in_order(submissions):
    """Oldest first. GRA must have a sale's invoice before it can accept that sale's refund."""
    stuck = set()
    for sub in submissions.exclude(status=Status.ACCEPTED).select_related("sale"):
        if sub.sale_id not in stuck and not _send(sub):
            stuck.add(sub.sale_id)


def send_for(sale):
    """Call after the transaction commits. Never raises: the sale has already happened."""
    _send_in_order(sale.evat_submissions.all())
    sale.refresh_from_db(fields=["evat_status", "evat_reference"])


def send_all():
    _send_in_order(EvatSubmission.objects.all())
