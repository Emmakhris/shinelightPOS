from datetime import datetime, time, timedelta

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import ExtractHour, TruncDate
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts.permissions import HasPerm
from apps.business.models import Branch, Expense
from apps.catalog.models import Variant
from apps.common.csvexport import csv_response, wants_csv
from apps.common.money import ZERO, D, money
from apps.customers.models import Customer, CustomerTransaction
from apps.inventory.models import StockLevel
from apps.restaurant.models import Order
from apps.sales.models import Payment, Refund, RefundLine, Sale, SaleLine, SaleTax
from apps.shifts.models import CashMovement, Shift
from apps.shifts.services import build_report

ReportsPerm = HasPerm("view_reports")


def _parse_date(value, default):
    if not value:
        return default
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError({"detail": f"Bad date '{value}'. Use YYYY-MM-DD."})


def date_range(request):
    """?start=YYYY-MM-DD&end=YYYY-MM-DD, both inclusive, in the shop's time zone. Defaults to today."""
    today = timezone.localdate()
    start = _parse_date(request.query_params.get("start"), today)
    end = _parse_date(request.query_params.get("end"), start)
    if end < start:
        start, end = end, start
    tz = timezone.get_current_timezone()
    return (
        start, end,
        timezone.make_aware(datetime.combine(start, time.min), tz),
        timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min), tz),
    )


def _scoped(request):
    start, end, since, until = date_range(request)
    sales = Sale.objects.filter(created_at__gte=since, created_at__lt=until)
    refunds = Refund.objects.filter(created_at__gte=since, created_at__lt=until)
    return start, end, since, until, sales, refunds


def _s(v):
    return str(money(v or ZERO))


@api_view(["GET"])
@permission_classes([ReportsPerm])
def summary(request):
    start, end, since, until, sales, refunds = _scoped(request)
    report = build_report(
        sales, refunds,
        CashMovement.objects.filter(created_at__gte=since, created_at__lt=until),
        CustomerTransaction.objects.filter(kind=CustomerTransaction.Kind.CREDIT_PAYMENT,
                                           created_at__gte=since, created_at__lt=until),
    )
    report.pop("opening_float")
    report.pop("expected_cash")
    kept = sales.exclude(status=Sale.Status.VOIDED)
    refund_tax = refunds.aggregate(t=Sum("tax_amount"))["t"] or ZERO
    refund_amount = D(report["refunds"])
    # Approximate cost of refunded goods using each refunded line's cost.
    refund_cost = sum(
        (rl.quantity * rl.sale_line.unit_cost for rl in RefundLine.objects.filter(refund__in=refunds).select_related("sale_line")),
        ZERO,
    )
    net_sales = D(report["net_sales"]) - (refund_amount - refund_tax)
    cost = D(report["cost_of_sales"]) - refund_cost
    gross_profit = net_sales - cost
    expenses = Expense.objects.filter(date__gte=start, date__lte=end).aggregate(t=Sum("amount"))["t"] or ZERO
    count = report["sales_count"] or 0

    by_day = [
        {"date": r["day"].isoformat(), "count": r["count"], "total": _s(r["total"])}
        for r in kept.annotate(day=TruncDate("created_at")).values("day")
        .annotate(count=Count("pk"), total=Sum("total")).order_by("day")
    ]
    by_hour = {r["hour"]: r for r in kept.annotate(hour=ExtractHour("created_at")).values("hour")
               .annotate(count=Count("pk"), total=Sum("total"))}
    hours = [{"hour": h, "count": by_hour.get(h, {}).get("count", 0), "total": _s(by_hour.get(h, {}).get("total"))}
             for h in range(24)]
    if wants_csv(request):
        return csv_response("sales-by-day.csv", [("date", "Date"), ("count", "Sales"), ("total", "Total")], by_day)
    report.update({
        "start": start.isoformat(), "end": end.isoformat(),
        "net_sales_after_refunds": _s(net_sales),
        "cost_after_refunds": _s(cost),
        "gross_profit": _s(gross_profit),
        "gross_margin_percent": str(round(gross_profit / net_sales * 100, 1)) if net_sales else "0",
        "expenses": _s(expenses),
        "net_profit": _s(gross_profit - expenses),
        "average_sale": _s(D(report["gross_sales"]) / count) if count else "0.00",
        "by_day": by_day,
        "by_hour": hours,
    })
    return Response(report)


def _line_rows(request, group_fields, label_field):
    _, _, _, _, sales, _ = _scoped(request)
    lines = SaleLine.objects.filter(sale__in=sales.exclude(status=Sale.Status.VOIDED))
    cost_expr = ExpressionWrapper(F("unit_cost") * F("quantity"), output_field=DecimalField(max_digits=18, decimal_places=4))
    rows = (
        lines.values(*group_fields)
        .annotate(qty=Sum("quantity"), refunded=Sum("refunded_quantity"), revenue=Sum("total"),
                  net=Sum("net_amount"), tax=Sum("tax_amount"), discount=Sum("discount"), cost=Sum(cost_expr))
        .order_by("-revenue")
    )
    out = []
    for r in rows:
        net, cost = r["net"] or ZERO, r["cost"] or ZERO
        out.append({
            "name": r[label_field] or "(none)",
            "quantity": str((r["qty"] or ZERO).normalize()),
            "refunded_quantity": str((r["refunded"] or ZERO).normalize()),
            "revenue": _s(r["revenue"]), "discount": _s(r["discount"]), "tax": _s(r["tax"]),
            "net": _s(net), "cost": _s(cost), "profit": _s(net - cost),
        })
    return out


LINE_COLUMNS = [("name", "Name"), ("quantity", "Qty sold"), ("refunded_quantity", "Qty refunded"),
                ("revenue", "Revenue"), ("discount", "Discount"), ("tax", "Tax"), ("net", "Net sales"),
                ("cost", "Cost"), ("profit", "Gross profit")]


@api_view(["GET"])
@permission_classes([ReportsPerm])
def products(request):
    rows = _line_rows(request, ["variant", "name"], "name")
    if wants_csv(request):
        return csv_response("sales-by-product.csv", LINE_COLUMNS, rows)
    return Response(rows)


@api_view(["GET"])
@permission_classes([ReportsPerm])
def categories(request):
    rows = _line_rows(request, ["variant__product__category__name"], "variant__product__category__name")
    if wants_csv(request):
        return csv_response("sales-by-category.csv", LINE_COLUMNS, rows)
    return Response(rows)


@api_view(["GET"])
@permission_classes([ReportsPerm])
def cashiers(request):
    _, _, _, _, sales, refunds = _scoped(request)
    refund_map = {r["user"]: r["total"] for r in refunds.values("user").annotate(total=Sum("amount"))}
    rows = []
    for r in (sales.exclude(status=Sale.Status.VOIDED).values("cashier", "cashier__first_name", "cashier__last_name",
                                                              "cashier__username")
              .annotate(count=Count("pk"), total=Sum("total"), discounts=Sum("discount_total")).order_by("-total")):
        name = f"{r['cashier__first_name']} {r['cashier__last_name']}".strip() or r["cashier__username"]
        rows.append({
            "name": name, "sales_count": r["count"], "total": _s(r["total"]), "discounts": _s(r["discounts"]),
            "refunds": _s(refund_map.get(r["cashier"])),
            "voids": sales.filter(status=Sale.Status.VOIDED, cashier=r["cashier"]).count(),
        })
    if wants_csv(request):
        return csv_response("sales-by-cashier.csv", [(k, k) for k in
                            ["name", "sales_count", "total", "discounts", "refunds", "voids"]], rows)
    return Response(rows)


@api_view(["GET"])
@permission_classes([ReportsPerm])
def payments(request):
    _, _, _, _, sales, refunds = _scoped(request)
    kept = sales.exclude(status=Sale.Status.VOIDED)
    refund_map = {r["method"]: r["total"] for r in refunds.values("method").annotate(total=Sum("amount"))}
    change = kept.aggregate(t=Sum("change_due"))["t"] or ZERO
    rows = []
    for r in Payment.objects.filter(sale__in=kept).values("method").annotate(count=Count("pk"), total=Sum("amount")):
        total = r["total"] - (change if r["method"] == "cash" else ZERO)
        rows.append({"method": r["method"], "count": r["count"], "total": _s(total),
                     "refunds": _s(refund_map.get(r["method"])), "net": _s(total - (refund_map.get(r["method"]) or ZERO))})
    momo = [
        {"network": r["momo_network"] or "unspecified", "count": r["count"], "total": _s(r["total"])}
        for r in Payment.objects.filter(sale__in=kept, method="momo").values("momo_network")
        .annotate(count=Count("pk"), total=Sum("amount"))
    ]
    if wants_csv(request):
        return csv_response("payments.csv", [(k, k) for k in ["method", "count", "total", "refunds", "net"]], rows)
    return Response({"methods": rows, "momo_networks": momo})


@api_view(["GET"])
@permission_classes([ReportsPerm])
def tax(request):
    """VAT / levy report for filing. Refund tax is shared across the taxes in proportion to what was collected."""
    _, _, _, _, sales, refunds = _scoped(request)
    kept = sales.exclude(status=Sale.Status.VOIDED)
    collected = list(SaleTax.objects.filter(sale__in=kept).values("code", "name", "rate").annotate(amount=Sum("amount")))
    total_collected = sum((r["amount"] for r in collected), ZERO)
    refund_tax = refunds.aggregate(t=Sum("tax_amount"))["t"] or ZERO
    rows = []
    for r in collected:
        share = money(refund_tax * r["amount"] / total_collected) if total_collected else ZERO
        rows.append({"code": r["code"], "name": r["name"], "rate": str(r["rate"]), "collected": _s(r["amount"]),
                     "refunded": _s(share), "net": _s(r["amount"] - share)})
    by_category = {
        r["tax_category"]: r for r in SaleLine.objects.filter(sale__in=kept).values("tax_category")
        .annotate(net=Sum("net_amount"), gross=Sum("total"))
    }
    if wants_csv(request):
        return csv_response("tax.csv", [(k, k) for k in ["code", "name", "rate", "collected", "refunded", "net"]], rows)
    return Response({
        "taxes": rows,
        "total_collected": _s(total_collected), "total_refunded": _s(refund_tax),
        "net_tax": _s(total_collected - refund_tax),
        "standard_rated_net": _s(by_category.get("standard", {}).get("net")),
        "zero_rated": _s(by_category.get("zero", {}).get("gross")),
        "exempt": _s(by_category.get("exempt", {}).get("gross")),
    })


@api_view(["GET"])
@permission_classes([ReportsPerm])
def inventory_valuation(request):
    branch = Branch.default()
    levels = dict(StockLevel.objects.filter(branch=branch).values_list("variant_id", "quantity"))
    rows = []
    cost_total = retail_total = ZERO
    for v in Variant.objects.filter(is_active=True, product__track_stock=True, product__is_active=True).select_related(
            "product__category"):
        qty = levels.get(v.pk, ZERO)
        cost, retail = qty * v.cost_price, qty * v.price
        cost_total += cost
        retail_total += retail
        rows.append({"name": v.full_name, "category": v.product.category.name if v.product.category else "",
                     "quantity": str(qty.normalize()), "cost_price": str(v.cost_price), "price": str(v.price),
                     "cost_value": _s(cost), "retail_value": _s(retail)})
    rows.sort(key=lambda r: -D(r["cost_value"]))
    if wants_csv(request):
        return csv_response("inventory-valuation.csv", [(k, k) for k in rows[0]] if rows else [("name", "name")], rows)
    return Response({"items": rows, "cost_value": _s(cost_total), "retail_value": _s(retail_total),
                     "potential_profit": _s(retail_total - cost_total)})


@api_view(["GET"])
@permission_classes([ReportsPerm])
def z_report(request):
    """End-of-day report for every till: ?date=YYYY-MM-DD."""
    day = _parse_date(request.query_params.get("date"), timezone.localdate())
    tz = timezone.get_current_timezone()
    since = timezone.make_aware(datetime.combine(day, time.min), tz)
    until = since + timedelta(days=1)
    shifts = Shift.objects.filter(opened_at__lt=until).filter(
        closed_at__isnull=True
    ) | Shift.objects.filter(opened_at__lt=until, closed_at__gte=since)
    report = build_report(
        Sale.objects.filter(created_at__gte=since, created_at__lt=until),
        Refund.objects.filter(created_at__gte=since, created_at__lt=until),
        CashMovement.objects.filter(created_at__gte=since, created_at__lt=until),
        CustomerTransaction.objects.filter(kind=CustomerTransaction.Kind.CREDIT_PAYMENT,
                                           created_at__gte=since, created_at__lt=until),
    )
    report.pop("opening_float")
    report.pop("expected_cash")
    report["date"] = day.isoformat()
    report["shifts"] = [
        {"id": s.pk, "cashier": s.user.display_name, "register_name": s.register_name, "status": s.status,
         "opened_at": s.opened_at.isoformat(), "closed_at": s.closed_at.isoformat() if s.closed_at else None,
         "expected_cash": None if s.expected_cash is None else str(s.expected_cash),
         "counted_cash": None if s.counted_cash is None else str(s.counted_cash),
         "difference": None if s.difference is None else str(s.difference)}
        for s in shifts.distinct().select_related("user").order_by("opened_at")
    ]
    return Response(report)


def _last_backup_iso():
    from apps.business.backups import last_backup_time

    when = last_backup_time()
    return when.isoformat() if when else None


@api_view(["GET"])
@permission_classes([HasPerm("sell")])
def dashboard(request):
    today = timezone.localdate()
    tz = timezone.get_current_timezone()
    since = timezone.make_aware(datetime.combine(today, time.min), tz)
    yesterday = since - timedelta(days=1)

    def totals(a, b):
        agg = Sale.objects.filter(created_at__gte=a, created_at__lt=b).exclude(status=Sale.Status.VOIDED).aggregate(
            count=Count("pk"), total=Sum("total"))
        return {"count": agg["count"], "total": _s(agg["total"])}

    data = {"today": totals(since, since + timedelta(days=1)), "yesterday": totals(yesterday, since)}
    if request.user.has_pos_perm("view_reports"):
        low = 0
        levels = dict(StockLevel.objects.filter(branch=Branch.default()).values_list("variant_id", "quantity"))
        for v in Variant.objects.filter(is_active=True, product__is_active=True, product__track_stock=True).select_related(
                "product"):
            if levels.get(v.pk, ZERO) <= v.product.low_stock_threshold:
                low += 1
        data.update({
            "low_stock_count": low,
            "open_shifts": Shift.objects.filter(status=Shift.Status.OPEN).count(),
            "open_orders": Order.objects.filter(status=Order.Status.OPEN).count(),
            "customers_owing": _s(Customer.objects.aggregate(t=Sum("balance"))["t"]),
            "last_backup_at": _last_backup_iso(),
            # With no ?start/end in the query string this covers today.
            "top_products": _line_rows(request, ["variant", "name"], "name")[:5],
        })
    return Response(data)
