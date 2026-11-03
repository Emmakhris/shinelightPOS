import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.restaurant.models import FloorArea, Order, Table
from conftest import make_item

pytestmark = pytest.mark.django_db


def test_setup_wizard_runs_once_and_seeds_demo_data():
    client = APIClient()
    assert client.get("/api/setup/status/").data["setup_complete"] is False
    body = {
        "business_name": "Shine Light Mart", "owner_first_name": "Kwame", "owner_username": "kwame",
        "owner_password": "secret123", "owner_pin": "2468", "vat_registered": True, "restaurant_mode": True,
        "demo_data": True,
    }
    r = client.post("/api/setup/", body, format="json")
    assert r.status_code == 201, r.data
    assert User.objects.get(username="kwame").role == "owner"
    assert client.post("/api/setup/", body, format="json").status_code == 400
    login = client.post("/api/auth/login/", {"username": "kwame", "password": "secret123"})
    assert login.status_code == 200 and "access" in login.data
    pin = client.post("/api/auth/pin-login/", {"user_id": login.data["user"]["id"], "pin": "2468"})
    assert pin.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {pin.data['access']}")
    items = client.get("/api/catalog/pos-items/").data
    assert any(i["name"] == "Jollof Rice" for i in items)
    assert len(client.get("/api/restaurant/floor/").data) == 2


def test_restaurant_order_send_to_kitchen_and_pay(cashier_api, cashier_shift, business):
    area = FloorArea.objects.create(name="Hall")
    t1 = Table.objects.create(area=area, name="T1")
    t2 = Table.objects.create(area=area, name="T2")
    waakye = make_item("Waakye", "10.00", track_stock=False, is_kitchen_item=True)
    beer = make_item("Club Beer", "15.00", stock=10)

    order = cashier_api.post("/api/restaurant/orders/", {"table": t1.pk, "order_type": "dine_in", "guests": 2}).data
    assert cashier_api.post("/api/restaurant/orders/", {"table": t1.pk, "order_type": "dine_in"}).status_code == 400
    base = f"/api/restaurant/orders/{order['id']}"
    cashier_api.post(f"{base}/items/", {"variant": waakye.pk, "quantity": 2}, format="json")
    cashier_api.post(f"{base}/items/", {"variant": beer.pk}, format="json")
    sent = cashier_api.post(f"{base}/send/").data
    assert [i["name"] for i in sent["ticket"]["items"]] == ["Waakye"]  # the bar item is not on the kitchen ticket
    assert cashier_api.post(f"{base}/send/").status_code == 400

    cashier_api.post(f"{base}/items/", {"variant": waakye.pk}, format="json")
    second = cashier_api.post(f"{base}/send/").data["ticket"]
    assert second["number"] == 2 and second["items"][0]["quantity"] == "1.000"

    moved = cashier_api.post(f"{base}/move/", {"table": t2.pk}).data
    assert moved["table_name"] == "T2"
    bill = cashier_api.post(f"{base}/bill/").data
    assert bill["total"] == "45.00"
    paid = cashier_api.post(f"{base}/pay/", {"payments": [{"method": "cash", "amount": "50"}]}, format="json")
    assert paid.status_code == 201, paid.data
    assert paid.data["order_type"] == "dine_in" and paid.data["table_name"] == "T2"
    assert Order.objects.get(pk=order["id"]).status == "paid"
    floor = cashier_api.get("/api/restaurant/floor/").data
    assert all(t["order"] is None for t in floor[0]["tables"])


def test_removing_sent_item_needs_approval(cashier_api, manager, business):
    waakye = make_item("Waakye", "10.00", track_stock=False, is_kitchen_item=True)
    order = cashier_api.post("/api/restaurant/orders/", {"order_type": "takeaway", "customer_label": "Yaw"}).data
    base = f"/api/restaurant/orders/{order['id']}"
    item = cashier_api.post(f"{base}/items/", {"variant": waakye.pk}, format="json").data["items"][0]
    cashier_api.post(f"{base}/send/")
    assert cashier_api.delete(f"{base}/items/{item['id']}/").status_code == 403
    r = cashier_api.delete(f"{base}/items/{item['id']}/", {"approval_pin": "1234"}, format="json")
    assert r.status_code == 200 and r.data["items"][0]["status"] == "cancelled"


def test_purchase_order_receiving_updates_stock_and_cost(owner_api, business):
    soap = make_item("Soap", "7.00", cost="5.00", stock=0)
    sup = owner_api.post("/api/inventory/suppliers/", {"name": "Wholesaler"}).data
    po = owner_api.post("/api/inventory/purchase-orders/", {
        "supplier": sup["id"], "lines": [{"variant": soap.pk, "quantity_ordered": "24", "unit_cost": "5.50"}],
    }, format="json").data
    line = po["lines"][0]["id"]
    part = owner_api.post(f"/api/inventory/purchase-orders/{po['id']}/receive/",
                          {"lines": [{"line": line, "quantity": "12"}]}, format="json").data
    assert part["status"] == "partial"
    full = owner_api.post(f"/api/inventory/purchase-orders/{po['id']}/receive/",
                          {"lines": [{"line": line, "quantity": "12"}]}, format="json").data
    assert full["status"] == "received"
    stock = {r["name"]: r for r in owner_api.get("/api/inventory/stock/").data}
    assert stock["Soap"]["quantity"] == "24.000" and stock["Soap"]["cost_price"] == "5.50"


def test_stock_count_records_only_differences(owner_api, business):
    a = make_item("A", "1.00", stock=10)
    b = make_item("B", "1.00", stock=5)
    r = owner_api.post("/api/inventory/count/", {"lines": [{"variant": a.pk, "counted": "8"},
                                                          {"variant": b.pk, "counted": "5"}]}, format="json")
    assert len(r.data["changed"]) == 1 and r.data["changed"][0]["change"] == "-2.000"


def test_reports_respond(owner_api, cashier_api, cashier_shift, soda):
    cashier_api.post("/api/sales/checkout/", {"lines": [{"variant": soda.pk, "quantity": 2}],
                                              "payments": [{"method": "cash", "amount": "24"}]}, format="json")
    s = owner_api.get("/api/reports/summary/").data
    assert s["gross_sales"] == "24.00" and s["net_sales"] == "20.00" and s["gross_profit"] == "6.00"
    tax = owner_api.get("/api/reports/tax/").data
    assert tax["total_collected"] == "4.00"
    assert owner_api.get("/api/reports/products/").data[0]["name"] == "Soda"
    for path in ["categories", "cashiers", "payments", "inventory-valuation", "z", "dashboard"]:
        assert owner_api.get(f"/api/reports/{path}/").status_code == 200, path
    csv = owner_api.get("/api/reports/products/?export=csv")
    assert csv["Content-Type"] == "text/csv" and b"Soda" in csv.content
    assert cashier_api.get("/api/reports/summary/").status_code == 403
