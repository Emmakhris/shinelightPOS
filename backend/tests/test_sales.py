from decimal import Decimal as D

import pytest

from apps.customers.models import Customer
from apps.inventory.models import StockLevel, StockMovement
from apps.sales.models import Sale
from conftest import api_for, make_item

pytestmark = pytest.mark.django_db


def stock_of(variant):
    return StockLevel.objects.get(variant=variant).quantity


def sell(api, lines, payments, **extra):
    return api.post("/api/sales/checkout/", {"lines": lines, "payments": payments, **extra}, format="json")


def test_cash_sale_takes_stock_numbers_invoice_and_gives_change(cashier_api, cashier_shift, soda):
    r = sell(cashier_api, [{"variant": soda.pk, "quantity": 2}], [{"method": "cash", "amount": "30.00"}])
    assert r.status_code == 201, r.data
    assert r.data["total"] == "24.00"
    assert r.data["tax_total"] == "4.00"  # 24.00 includes 20% of levies + VAT
    assert r.data["change_due"] == "6.00"
    assert r.data["invoice_number"] == "INV-MAIN-000001"
    assert stock_of(soda) == 8
    assert StockMovement.objects.filter(variant=soda, reason="sale", change=-2).exists()
    r2 = sell(cashier_api, [{"variant": soda.pk, "quantity": 1}], [{"method": "cash", "amount": "12.00"}])
    assert r2.data["invoice_number"] == "INV-MAIN-000002"


def test_split_payment_cash_and_momo(cashier_api, cashier_shift, soda):
    r = sell(cashier_api, [{"variant": soda.pk, "quantity": 2}], [
        {"method": "momo", "amount": "10.00", "momo_network": "mtn", "reference": "TX123"},
        {"method": "cash", "amount": "20.00"},
    ])
    assert r.status_code == 201, r.data
    assert r.data["change_due"] == "6.00"
    assert {p["method"] for p in r.data["payments"]} == {"cash", "momo"}


def test_short_payment_and_momo_overpayment_are_rejected(cashier_api, cashier_shift, soda):
    short = sell(cashier_api, [{"variant": soda.pk, "quantity": 2}], [{"method": "cash", "amount": "20.00"}])
    assert short.status_code == 400 and "short" in short.data["detail"]
    over = sell(cashier_api, [{"variant": soda.pk, "quantity": 2}], [{"method": "momo", "amount": "30.00"}])
    assert over.status_code == 400
    assert Sale.objects.count() == 0


def test_cannot_sell_more_than_in_stock_and_nothing_is_saved(cashier_api, cashier_shift, soda):
    r = sell(cashier_api, [{"variant": soda.pk, "quantity": 11}], [{"method": "cash", "amount": "200.00"}])
    assert r.status_code == 400 and r.data["code"] == "insufficient_stock"
    assert Sale.objects.count() == 0
    assert stock_of(soda) == 10


def test_sale_requires_open_shift(cashier_api, soda):
    r = sell(cashier_api, [{"variant": soda.pk, "quantity": 1}], [{"method": "cash", "amount": "12.00"}])
    assert r.status_code == 400 and r.data["code"] == "no_open_shift"


def test_whole_units_only_unless_sold_by_weight(cashier_api, cashier_shift, soda, rice):
    bad = sell(cashier_api, [{"variant": soda.pk, "quantity": "1.5"}], [{"method": "cash", "amount": "50"}])
    assert bad.status_code == 400
    ok = sell(cashier_api, [{"variant": rice.pk, "quantity": "1.5"}], [{"method": "cash", "amount": "27.00"}])
    assert ok.status_code == 201 and ok.data["total"] == "27.00" and ok.data["tax_total"] == "0.00"


def test_big_discount_needs_manager_pin(cashier_api, cashier_shift, manager, soda):
    lines = [{"variant": soda.pk, "quantity": 2}]
    pay = [{"method": "cash", "amount": "19.20"}]
    denied = sell(cashier_api, lines, pay, discount_type="percent", discount_value="20")
    assert denied.status_code == 403 and denied.data["code"] == "approval_required"
    wrong = sell(cashier_api, lines, pay, discount_type="percent", discount_value="20", approval_pin="0000")
    assert wrong.status_code == 403
    ok = sell(cashier_api, lines, pay, discount_type="percent", discount_value="20", approval_pin="1234")
    assert ok.status_code == 201, ok.data
    assert ok.data["total"] == "19.20" and ok.data["discount_total"] == "4.80"
    assert ok.data["approved_by_name"] == manager.display_name


def test_quote_matches_checkout(cashier_api, cashier_shift, soda, rice):
    body = {"lines": [{"variant": soda.pk, "quantity": 3, "discount_value": "1.00"},
                      {"variant": rice.pk, "quantity": "2.25"}],
            "discount_type": "amount", "discount_value": "2.00"}
    q = cashier_api.post("/api/sales/quote/", body, format="json")
    assert q.status_code == 200, q.data
    s = sell(cashier_api, body["lines"], [{"method": "cash", "amount": "100"}],
             discount_type="amount", discount_value="2.00")
    assert s.status_code == 201, s.data
    for key in ["subtotal", "discount_total", "tax_total", "total"]:
        assert q.data[key] == s.data[key]


def test_refund_needs_approval_restocks_and_updates_status(cashier_api, cashier_shift, soda):
    sale = sell(cashier_api, [{"variant": soda.pk, "quantity": 2}], [{"method": "cash", "amount": "24"}]).data
    line_id = sale["lines"][0]["id"]
    url = f"/api/sales/{sale['id']}/refund/"
    body = {"lines": [{"line": line_id, "quantity": 1}], "method": "cash", "reason": "Damaged"}
    assert cashier_api.post(url, body, format="json").status_code == 403
    r = cashier_api.post(url, {**body, "approval_pin": "9999"}, format="json")  # no manager yet
    assert r.status_code == 403
    from conftest import make_user
    make_user("boss", "manager", "4321")
    r = cashier_api.post(url, {**body, "approval_pin": "4321"}, format="json")
    assert r.status_code == 201, r.data
    assert r.data["amount"] == "12.00"
    assert stock_of(soda) == 9
    assert Sale.objects.get(pk=sale["id"]).status == "partially_refunded"
    too_many = cashier_api.post(url, {**body, "lines": [{"line": line_id, "quantity": 2}], "approval_pin": "4321"},
                                format="json")
    assert too_many.status_code == 400
    cashier_api.post(url, {**body, "approval_pin": "4321"}, format="json")
    assert Sale.objects.get(pk=sale["id"]).status == "refunded"


def test_shift_report_and_close(cashier_api, cashier_shift, owner, soda):
    sell(cashier_api, [{"variant": soda.pk, "quantity": 2}], [{"method": "cash", "amount": "50"}])
    sell(cashier_api, [{"variant": soda.pk, "quantity": 1}], [{"method": "momo", "amount": "12", "reference": "x"}])
    url = f"/api/shifts/{cashier_shift.pk}/cash-movements/"
    assert cashier_api.post(url, {"kind": "paid_in", "amount": "10", "reason": "Float top-up"}).status_code == 201
    assert cashier_api.post(url, {"kind": "paid_out", "amount": "5", "reason": "Water"}).status_code == 201
    sale = Sale.objects.order_by("pk").first()
    api_for(owner).post(f"/api/sales/{sale.pk}/refund/", {
        "lines": [{"line": sale.lines.first().pk, "quantity": 1}], "method": "cash", "reason": "Return",
    }, format="json")
    # 100 float + 24 cash sale + 10 in - 5 out; owner refunded with no shift of their own
    report = cashier_api.get(f"/api/shifts/{cashier_shift.pk}/report/").data
    assert report["payments"] == {"cash": "24.00", "momo": "12.00"}
    assert report["expected_cash"] == "129.00"
    closed = cashier_api.post(f"/api/shifts/{cashier_shift.pk}/close/", {"counted_cash": "127.00"}).data
    assert closed["type"] == "Z" and closed["difference"] == "-2.00"


def test_owner_refund_in_cash_needs_their_own_open_shift(owner, cashier_api, cashier_shift, soda):
    sale = sell(cashier_api, [{"variant": soda.pk, "quantity": 1}], [{"method": "cash", "amount": "12"}]).data
    r = api_for(owner).post(f"/api/sales/{sale['id']}/refund/", {
        "lines": [{"line": sale["lines"][0]["id"], "quantity": 1}], "method": "cash", "reason": "x",
    }, format="json")
    assert r.status_code == 400 and r.data["code"] == "no_open_shift"


def test_credit_sale_and_points(cashier_api, cashier_shift, soda, business):
    ama = Customer.objects.create(name="Ama", credit_limit=D("30.00"))
    r = sell(cashier_api, [{"variant": soda.pk, "quantity": 2}], [{"method": "credit", "amount": "24"}],
             customer=ama.pk)
    assert r.status_code == 201, r.data
    ama.refresh_from_db()
    assert ama.balance == D("24.00")
    assert ama.loyalty_points == D("24.00")  # 1 point per cedi by default
    over = sell(cashier_api, [{"variant": soda.pk, "quantity": 1}], [{"method": "credit", "amount": "12"}],
                customer=ama.pk)
    assert over.status_code == 400 and over.data["code"] == "credit_limit"
    # 20 points x GHS 0.05 = GHS 1.00 off
    pts = sell(cashier_api, [{"variant": soda.pk, "quantity": 1}],
               [{"method": "points", "amount": "1.00"}, {"method": "cash", "amount": "11.00"}], customer=ama.pk)
    assert pts.status_code == 201, pts.data
    ama.refresh_from_db()
    assert ama.loyalty_points == D("24.00") - D("20.00") + D("11.00")
    pay = cashier_api.post(f"/api/customers/{ama.pk}/pay_balance/", {"amount": "10", "method": "cash"})
    assert pay.status_code == 200 and pay.data["balance"] == "14.00"


def test_void_restocks_and_leaves_reports(cashier_api, cashier_shift, manager, soda):
    sale = sell(cashier_api, [{"variant": soda.pk, "quantity": 3}], [{"method": "cash", "amount": "36"}]).data
    r = cashier_api.post(f"/api/sales/{sale['id']}/void/", {"reason": "Wrong item", "approval_pin": "1234"})
    assert r.status_code == 200 and r.data["status"] == "voided"
    assert stock_of(soda) == 10
    report = cashier_api.get(f"/api/shifts/{cashier_shift.pk}/report/").data
    assert report["sales_count"] == 0 and report["voided_count"] == 1 and report["expected_cash"] == "100.00"


def test_price_override_needs_approval(cashier_api, cashier_shift, manager, soda):
    lines = [{"variant": soda.pk, "quantity": 1, "unit_price": "10.00"}]
    assert sell(cashier_api, lines, [{"method": "cash", "amount": "10"}]).status_code == 403
    ok = sell(cashier_api, lines, [{"method": "cash", "amount": "10"}], approval_pin="1234")
    assert ok.status_code == 201 and ok.data["total"] == "10.00"


def test_barcode_lookup_and_permissions(cashier_api, owner_api, soda):
    assert cashier_api.get("/api/catalog/lookup/?code=111").data["id"] == soda.pk
    assert cashier_api.get("/api/catalog/lookup/?code=nope").status_code == 404
    new = {"name": "Bread", "variants": [{"price": "10.00", "barcodes": ["999"], "opening_stock": "5"}]}
    assert cashier_api.post("/api/catalog/products/", new, format="json").status_code == 403
    r = owner_api.post("/api/catalog/products/", new, format="json")
    assert r.status_code == 201, r.data
    assert r.data["variants"][0]["barcodes"] == ["999"]
    dup = owner_api.post("/api/catalog/products/", {**new, "name": "Bread 2"}, format="json")
    assert dup.status_code == 400  # barcode already used


def test_exclusive_pricing(cashier_api, cashier_shift, soda, business):
    business.prices_include_tax = False
    business.save()
    r = sell(cashier_api, [{"variant": soda.pk, "quantity": 1}], [{"method": "cash", "amount": "14.40"}])
    assert r.status_code == 201, r.data
    assert r.data["total"] == "14.40" and r.data["tax_total"] == "2.40"


def test_modifiers_are_priced_and_validated(cashier_api, cashier_shift, business):
    from apps.catalog.models import Modifier, ModifierGroup
    jollof = make_item("Jollof", "12.00", track_stock=False)
    protein = ModifierGroup.objects.create(name="Protein", min_select=1, max_select=1)
    chicken = Modifier.objects.create(group=protein, name="Chicken", price=D("15.00"))
    fish = Modifier.objects.create(group=protein, name="Fish", price=D("20.00"))
    jollof.product.modifier_groups.add(protein)
    pay = [{"method": "cash", "amount": "50"}]
    assert sell(cashier_api, [{"variant": jollof.pk, "quantity": 1}], pay).status_code == 400  # protein required
    two = sell(cashier_api, [{"variant": jollof.pk, "quantity": 1, "modifiers": [chicken.pk, fish.pk]}], pay)
    assert two.status_code == 400
    ok = sell(cashier_api, [{"variant": jollof.pk, "quantity": 1, "modifiers": [chicken.pk]}], pay)
    assert ok.status_code == 201 and ok.data["total"] == "27.00"


def test_demo_dish_can_have_several_proteins(cashier_api, cashier_shift, business):
    from apps.business.demo import load_demo_data
    from apps.catalog.models import Modifier, Variant

    load_demo_data()
    jollof = Variant.objects.get(product__name="Jollof Rice")
    proteins = Modifier.objects.filter(group__name="Protein", name__in=["Chicken", "Fish", "Egg"])
    r = sell(cashier_api, [{"variant": jollof.pk, "quantity": 1, "modifiers": [m.pk for m in proteins]}],
             [{"method": "cash", "amount": "60"}])
    assert r.status_code == 201, r.data
    assert r.data["total"] == "52.00"  # 12.00 + 15.00 + 20.00 + 5.00
    assert len(r.data["lines"][0]["modifiers"]) == 3
