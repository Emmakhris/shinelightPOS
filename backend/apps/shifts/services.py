from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from apps.business.models import Branch, BusinessProfile
from apps.common.exceptions import BusinessError
from apps.common.money import ZERO, D, money

from .models import CashMovement, Shift


def current_shift(user):
    if not (user and user.is_authenticated):
        return None
    return Shift.objects.filter(user=user, status=Shift.Status.OPEN).first()


def require_shift(user):
    shift = current_shift(user)
    if shift is None and BusinessProfile.get().require_open_shift:
        raise BusinessError("Open a shift before taking payments.", code="no_open_shift")
    return shift


def open_shift(user, opening_float, register_name="Till 1"):
    if current_shift(user):
        raise BusinessError("You already have an open shift.")
    return Shift.objects.create(
        user=user, branch=Branch.default(), opening_float=money(opening_float), register_name=register_name
    )


def _sum(qs, field="amount"):
    return qs.aggregate(t=Sum(field))["t"] or ZERO


def build_report(sales, refunds, cash_movements, customer_payments, opening_float=ZERO):
    """
    Totals for a set of sales/refunds/cash movements. Used for a shift (X/Z report) and for a
    whole day across all tills. Every query is passed in so the caller decides the scope.
    """
    from apps.sales.models import Payment, SaleLine, SaleTax

    kept = sales.exclude(status="voided")
    voided = sales.filter(status="voided")
    totals = kept.aggregate(
        count=Count("pk"), gross=Sum("total"), discounts=Sum("discount_total"), tax=Sum("tax_total"),
        subtotal=Sum("subtotal"), change=Sum("change_due"), cost=Sum("cost_total"),
    )
    gross = totals["gross"] or ZERO

    payments = {
        row["method"]: row["total"]
        for row in Payment.objects.filter(sale__in=kept).values("method").annotate(total=Sum("amount"))
    }
    change = totals["change"] or ZERO
    if "cash" in payments:
        payments["cash"] -= change  # cash kept in the drawer, after giving change

    refunds_by_method = {
        row["method"]: row["total"] for row in refunds.values("method").annotate(total=Sum("amount"))
    }
    refund_total = sum(refunds_by_method.values(), ZERO)

    movements = {row["kind"]: row["total"] for row in cash_movements.values("kind").annotate(total=Sum("amount"))}
    balance_payments = {
        row["method"]: -row["total"]
        for row in customer_payments.values("method").annotate(total=Sum("amount"))
    }

    taxes = [
        {"code": r["code"], "name": r["name"], "amount": str(r["total"])}
        for r in SaleTax.objects.filter(sale__in=kept).values("code", "name").annotate(total=Sum("amount")).order_by("code")
    ]
    items_sold = _sum(SaleLine.objects.filter(sale__in=kept), "quantity")

    expected_cash = (
        D(opening_float) + payments.get("cash", ZERO) + balance_payments.get("cash", ZERO)
        + movements.get("paid_in", ZERO) - movements.get("paid_out", ZERO) - movements.get("drop", ZERO)
        - refunds_by_method.get("cash", ZERO)
    )
    s = lambda v: str(money(v))  # noqa: E731
    return {
        "sales_count": totals["count"],
        "items_sold": str(items_sold.normalize()) if items_sold else "0",
        "gross_sales": s(gross),
        "subtotal": s(totals["subtotal"] or ZERO),
        "discounts": s(totals["discounts"] or ZERO),
        "tax": s(totals["tax"] or ZERO),
        "net_sales": s(gross - (totals["tax"] or ZERO)),
        "cost_of_sales": s(totals["cost"] or ZERO),
        "refunds": s(refund_total),
        "refunds_by_method": {k: s(v) for k, v in refunds_by_method.items()},
        "net_after_refunds": s(gross - refund_total),
        "voided_count": voided.count(),
        "voided_total": s(_sum(voided, "total")),
        "payments": {k: s(v) for k, v in sorted(payments.items())},
        "balance_payments": {k: s(v) for k, v in balance_payments.items()},
        "taxes": taxes,
        "opening_float": s(opening_float),
        "cash_in": s(movements.get("paid_in", ZERO)),
        "cash_out": s(movements.get("paid_out", ZERO)),
        "cash_drops": s(movements.get("drop", ZERO)),
        "expected_cash": s(expected_cash),
    }


def shift_report(shift):
    from apps.sales.models import Refund, Sale

    report = build_report(
        Sale.objects.filter(shift=shift),
        Refund.objects.filter(shift=shift),
        shift.cash_movements.all(),
        shift.customer_payments.all(),
        opening_float=shift.opening_float,
    )
    report.update({
        "shift_id": shift.pk,
        "cashier": shift.user.display_name,
        "register_name": shift.register_name,
        "status": shift.status,
        "opened_at": shift.opened_at.isoformat(),
        "closed_at": shift.closed_at.isoformat() if shift.closed_at else None,
        "counted_cash": None if shift.counted_cash is None else str(shift.counted_cash),
        "difference": None if shift.difference is None else str(shift.difference),
        "type": "Z" if shift.status == Shift.Status.CLOSED else "X",
    })
    return report


def close_shift(shift, counted_cash, closed_by, note=""):
    with transaction.atomic():
        shift = Shift.objects.select_for_update().get(pk=shift.pk)
        if shift.status == Shift.Status.CLOSED:
            raise BusinessError("This shift is already closed.")
        report = shift_report(shift)
        shift.expected_cash = D(report["expected_cash"])
        shift.counted_cash = money(counted_cash)
        shift.difference = shift.counted_cash - shift.expected_cash
        shift.status = Shift.Status.CLOSED
        shift.closed_at = timezone.now()
        shift.closed_by = closed_by
        shift.closing_note = note
        shift.save()
        shift.report = shift_report(shift)
        shift.save(update_fields=["report"])
    return shift


def add_cash_movement(shift, kind, amount, reason, user, approved_by=None):
    if shift.status != Shift.Status.OPEN:
        raise BusinessError("The shift is closed.")
    if D(amount) <= 0:
        raise BusinessError("Enter an amount above zero.")
    return CashMovement.objects.create(
        shift=shift, kind=kind, amount=money(amount), reason=reason, user=user, approved_by=approved_by
    )
