from unittest import mock

import pytest

from apps.evat import connector
from apps.evat.models import EvatSubmission
from apps.sales.models import Sale

pytestmark = pytest.mark.django_db


@pytest.fixture
def evat_on(business):
    business.evat_enabled = True
    business.tin = "C0001234567"
    business.save()
    return business


def sell(api, variant, qty=2):
    r = api.post("/api/sales/checkout/", {"lines": [{"variant": variant.pk, "quantity": qty}],
                                          "payments": [{"method": "cash", "amount": "100"}]}, format="json")
    assert r.status_code == 201, r.data
    return r.data


def refund(api, sale):
    return api.post(f"/api/sales/{sale['id']}/refund/", {
        "lines": [{"line": sale["lines"][0]["id"], "quantity": 1}], "method": "cash", "reason": "Damaged",
        "approval_pin": "1234"}, format="json")


def test_off_by_default_and_nothing_is_reported(cashier_api, cashier_shift, soda, business):
    assert business.evat_enabled is False
    sale = sell(cashier_api, soda)
    assert sale["evat_status"] == "" and sale["evat_reference"] == ""
    assert not EvatSubmission.objects.exists()


def test_owner_switches_it_on(owner_api, cashier_api, cashier_shift, soda, business):
    assert cashier_api.patch("/api/settings/", {"evat_enabled": True}, format="json").status_code == 403
    assert owner_api.patch("/api/settings/", {"evat_enabled": True}, format="json").data["evat_enabled"] is True
    assert owner_api.get("/api/evat/").data["mode"] == "simulated"
    assert sell(cashier_api, soda)["evat_reference"].startswith("SIM-")


def test_sale_is_reported_with_its_details(cashier_api, cashier_shift, soda, evat_on):
    sale = sell(cashier_api, soda)
    assert sale["evat_status"] == "accepted"
    assert sale["evat_reference"] == f"SIM-{sale['invoice_number']}"
    sub = EvatSubmission.objects.get()
    assert sub.kind == "invoice" and sub.simulated is True
    p = sub.payload
    assert p["number"] == sale["invoice_number"] and p["seller"]["tin"] == "C0001234567"
    assert p["total"] == sale["total"] and len(p["lines"]) == 1 and p["lines"][0]["quantity"] == "2.000"
    assert {t["code"] for t in p["taxes"]} == {t["code"] for t in sale["taxes"]}


def test_sale_goes_through_when_gra_cannot_be_reached(owner_api, cashier_api, cashier_shift, soda, evat_on):
    with mock.patch.object(connector, "submit", side_effect=connector.EvatUnavailable("No internet")):
        sale = sell(cashier_api, soda)
    assert sale["evat_status"] == "pending" and sale["invoice_number"]
    sub = EvatSubmission.objects.get()
    assert sub.attempts == 1 and sub.message == "No internet"
    assert owner_api.get("/api/evat/").data["counts"]["pending"] == 1

    assert cashier_api.post("/api/evat/send/").status_code == 403
    assert owner_api.post("/api/evat/send/").data["counts"] == {"pending": 0, "accepted": 1, "rejected": 0}
    assert Sale.objects.get().evat_status == "accepted"
    # Accepted documents are not sent twice.
    with mock.patch.object(connector, "submit", side_effect=AssertionError):
        owner_api.post("/api/evat/send/")


def test_rejection_is_kept_and_shown(owner_api, cashier_api, cashier_shift, soda, evat_on):
    answer = {"accepted": False, "reference": "", "message": "Bad TIN"}
    with mock.patch.object(connector, "submit", return_value=answer):
        sale = sell(cashier_api, soda)
    assert sale["evat_status"] == "rejected"
    rows = owner_api.get("/api/evat/").data["submissions"]
    assert rows[0]["status"] == "rejected" and rows[0]["message"] == "Bad TIN"


def test_refund_and_void_are_reported(cashier_api, cashier_shift, manager, soda, evat_on):
    sale = sell(cashier_api, soda)
    r = refund(cashier_api, sale)
    assert r.status_code == 201
    sub = EvatSubmission.objects.get(kind="refund")
    assert sub.status == "accepted" and sub.number == r.data["number"]
    assert sub.payload["invoice"] == sale["invoice_number"] and sub.payload["total"] == r.data["amount"]

    other = sell(cashier_api, soda)
    voided = cashier_api.post(f"/api/sales/{other['id']}/void/", {"reason": "Mistake", "approval_pin": "1234"})
    assert voided.status_code == 200 and voided.data["evat_status"] == "accepted"
    sub = EvatSubmission.objects.get(kind="void")
    assert sub.number == f"{other['invoice_number']}-VOID" and sub.payload["reason"] == "Mistake"


def test_refund_waits_for_its_invoice(owner_api, cashier_api, cashier_shift, manager, soda, evat_on):
    sent = []

    def down(payload):
        sent.append(payload["number"])
        raise connector.EvatUnavailable("No internet")

    with mock.patch.object(connector, "submit", side_effect=down):
        sale = sell(cashier_api, soda)
        sent.clear()
        refund(cashier_api, sale)
    assert sent == [sale["invoice_number"]]  # tried the invoice again, and did not send the refund ahead of it

    owner_api.post("/api/evat/send/")
    assert list(EvatSubmission.objects.values_list("kind", "status")) == [("invoice", "accepted"), ("refund", "accepted")]


def test_sale_from_before_it_was_on_is_not_corrected_at_gra(cashier_api, cashier_shift, manager, soda, business):
    sale = sell(cashier_api, soda)
    business.evat_enabled = True
    business.save()
    assert refund(cashier_api, sale).status_code == 201
    assert not EvatSubmission.objects.exists()


def test_failed_sale_leaves_nothing_queued(cashier_api, cashier_shift, soda, evat_on):
    r = cashier_api.post("/api/sales/checkout/", {"lines": [{"variant": soda.pk, "quantity": 1}],
                                                  "payments": [{"method": "cash", "amount": "1"}]}, format="json")
    assert r.status_code == 400
    assert not EvatSubmission.objects.exists()
