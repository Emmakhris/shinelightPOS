import hashlib
import hmac
import json
from decimal import Decimal as D
from unittest import mock

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import AuditLog
from apps.payments import paystack
from apps.payments.models import PaystackRefund
from apps.sales.models import Refund

pytestmark = pytest.mark.django_db


@pytest.fixture
def fake_paystack(settings, business):
    settings.PAYSTACK_SECRET_KEY = "sk_fake"
    business.email = "shop@example.com"
    business.save()
    return settings


def paid_charge(api, amount="24.00", phone="0241234567"):
    ref = api.post("/api/payments/momo/", {"amount": amount, "phone": phone, "network": "mtn"},
                   format="json").data["reference"]
    assert api.get(f"/api/payments/momo/{ref}/?force=1").data["status"] == "success"
    return ref


def paystack_sale(api, soda, phone="0241234567", qty=2, amount="24.00"):
    ref = paid_charge(api, amount, phone)
    r = api.post("/api/sales/checkout/", {"lines": [{"variant": soda.pk, "quantity": qty}],
                                          "payments": [{"method": "momo", "amount": amount,
                                                        "paystack_reference": ref}]}, format="json")
    assert r.status_code == 201, r.data
    return r.data


def refund(api, sale, qty=1, **extra):
    body = {"lines": [{"line": sale["lines"][0]["id"], "quantity": qty}], "method": "momo", "reason": "Damaged",
            "through_paystack": True, "approval_pin": "1234", **extra}
    return api.post(f"/api/sales/{sale['id']}/refund/", body, format="json")


def test_refund_goes_back_through_paystack(cashier_api, cashier_shift, manager, soda, fake_paystack):
    sale = paystack_sale(cashier_api, soda)
    assert sale["payments"][0]["paystack"] == {"phone": "0241234567", "refundable": "24.00"}

    r = refund(cashier_api, sale)
    assert r.status_code == 201, r.data
    info = r.data["paystack"]
    assert info["status"] == "pending" and info["amount"] == "12.00" and info["phone"] == "0241234567"
    assert r.data["reference"] == info["reference"] and r.data["method"] == "momo"

    checked = cashier_api.post(f"/api/payments/refunds/{info['reference']}/check/").data
    assert checked["status"] == "processed" and checked["status_label"] == "Sent back"

    detail = cashier_api.get(f"/api/sales/{sale['id']}/").data
    assert detail["status"] == "partially_refunded"
    assert detail["refunds"][0]["paystack"]["status"] == "processed"
    assert detail["payments"][0]["paystack"]["refundable"] == "12.00"


def test_needs_manager_approval(cashier_api, cashier_shift, manager, soda, fake_paystack):
    sale = paystack_sale(cashier_api, soda)
    r = refund(cashier_api, sale, approval_pin="")
    assert r.status_code == 403 and r.data["code"] == "approval_required"
    assert not PaystackRefund.objects.exists() and not Refund.objects.exists()


def test_cannot_refund_more_than_the_charge(cashier_api, cashier_shift, manager, soda, fake_paystack):
    """The customer paid 10 by MoMo and 14 in cash, so only 10 can go back through Paystack."""
    ref = paid_charge(cashier_api, "10.00")
    sale = cashier_api.post("/api/sales/checkout/", {
        "lines": [{"variant": soda.pk, "quantity": 2}],
        "payments": [{"method": "momo", "amount": "10.00", "paystack_reference": ref},
                     {"method": "cash", "amount": "14.00"}]}, format="json").data
    r = refund(cashier_api, sale)
    assert r.status_code == 400 and r.data["code"] == "paystack_refund_limit"
    # Nothing was changed by the refused refund.
    assert not Refund.objects.exists()
    assert cashier_api.get(f"/api/sales/{sale['id']}/").data["lines"][0]["refunded_quantity"] == "0.000"


def test_sale_not_paid_through_paystack(cashier_api, cashier_shift, manager, soda, fake_paystack):
    sale = cashier_api.post("/api/sales/checkout/", {"lines": [{"variant": soda.pk, "quantity": 1}],
                                                     "payments": [{"method": "cash", "amount": "12.00"}]},
                            format="json").data
    assert refund(cashier_api, sale).status_code == 400
    assert refund(cashier_api, sale, method="cash").status_code == 400


def test_refused_refund_can_be_retried_or_paid_by_hand(cashier_api, cashier_shift, manager, soda, fake_paystack):
    sale = paystack_sale(cashier_api, soda, phone="0242222222")
    r = refund(cashier_api, sale)
    info = r.data["paystack"]
    # The goods came back, so the refund stands; the failure is shown so the customer still gets paid.
    assert r.status_code == 201 and info["status"] == "failed" and "balance" in info["message"]

    # Still owed, so it cannot be refunded twice.
    assert cashier_api.get(f"/api/sales/{sale['id']}/").data["payments"][0]["paystack"]["refundable"] == "12.00"

    denied = cashier_api.post(f"/api/payments/refunds/{info['reference']}/retry/", {}, format="json")
    assert denied.status_code == 403
    retried = cashier_api.post(f"/api/payments/refunds/{info['reference']}/retry/", {"approval_pin": "1234"},
                               format="json").data
    assert retried["status"] == "failed" and retried["reference"] != info["reference"]
    assert Refund.objects.get().reference == retried["reference"]
    assert AuditLog.objects.filter(action="paystack_refund_retried").exists()

    no_note = cashier_api.post(f"/api/payments/refunds/{retried['reference']}/settle/", {"approval_pin": "1234"},
                               format="json")
    assert no_note.status_code == 400
    settled = cashier_api.post(f"/api/payments/refunds/{retried['reference']}/settle/",
                               {"approval_pin": "1234", "note": "Paid in cash"}, format="json").data
    assert settled["status"] == "settled" and settled["message"] == "Paid in cash"
    # Final: a check does not contact Paystack, and it cannot be tried again.
    with mock.patch.object(paystack, "_call", side_effect=AssertionError):
        assert cashier_api.post(f"/api/payments/refunds/{retried['reference']}/check/").data["status"] == "settled"
    again = cashier_api.post(f"/api/payments/refunds/{retried['reference']}/retry/", {"approval_pin": "1234"},
                             format="json")
    assert again.status_code == 400


def test_failed_after_being_accepted(cashier_api, cashier_shift, manager, soda, fake_paystack):
    sale = paystack_sale(cashier_api, soda, phone="0243333333")
    info = refund(cashier_api, sale).data["paystack"]
    assert info["status"] == "pending"
    checked = cashier_api.post(f"/api/payments/refunds/{info['reference']}/check/").data
    assert checked["status"] == "failed" and "balance" in checked["message"]


def test_lost_connection_keeps_the_refund_and_sends_the_same_reference_again(
        cashier_api, cashier_shift, manager, soda, fake_paystack):
    sale = paystack_sale(cashier_api, soda)
    with mock.patch.object(paystack, "_call", side_effect=paystack.PaystackError("offline")):
        r = refund(cashier_api, sale)
    info = r.data["paystack"]
    assert r.status_code == 201 and info["status"] == "sending" and "reach Paystack" in info["message"]

    calls = []
    real = paystack._fake_call

    def spy(method, path, body=None):
        calls.append((method, path, body))
        return real(method, path, body)

    with mock.patch.object(paystack, "_call", side_effect=spy):
        checked = cashier_api.post(f"/api/payments/refunds/{info['reference']}/check/").data
    assert checked["status"] == "pending" and checked["reference"] == info["reference"]
    assert [c[0] for c in calls] == ["GET", "POST"] and calls[1][2]["reference"] == info["reference"]


def test_real_request_and_duplicate_reference(settings, cashier_api, cashier_shift, manager, soda, fake_paystack):
    sale = paystack_sale(cashier_api, soda)
    settings.PAYSTACK_SECRET_KEY = "sk_test_x"
    calls = []

    def fake_http(method, path, body=None):
        calls.append((method, path, body))
        if method == "POST":
            return {"status": False, "message": "already exists", "_http_status": 409}
        return {"status": True, "data": [{"status": "processing", "amount": 1200}]}

    with mock.patch.object(paystack, "_call", side_effect=fake_http):
        r = refund(cashier_api, sale).data["paystack"]
    body = calls[0][2]
    assert body["amount"] == 1200 and body["currency"] == "GHS" and body["reference"] == r["reference"]
    assert body["transaction"] == sale["payments"][0]["reference"]
    assert 8 <= len(r["reference"]) <= 64
    # A 409 means it already exists, not that it failed.
    assert calls[1][1] == f"/refund?reference={r['reference']}" and r["status"] == "processing"


def test_wrong_amount_from_paystack_needs_attention(settings, cashier_api, cashier_shift, manager, soda, fake_paystack):
    sale = paystack_sale(cashier_api, soda)
    settings.PAYSTACK_SECRET_KEY = "sk_test_x"
    with mock.patch.object(paystack, "_call", return_value={"status": True, "data": {"status": "processed", "amount": 100}}):
        r = refund(cashier_api, sale).data["paystack"]
    assert r["status"] == "needs-attention" and "instead of" in r["message"]


def test_paystack_sale_cannot_be_voided(cashier_api, cashier_shift, manager, soda, fake_paystack):
    sale = paystack_sale(cashier_api, soda)
    r = cashier_api.post(f"/api/sales/{sale['id']}/void/", {"reason": "Mistake", "approval_pin": "1234"})
    assert r.status_code == 400 and r.data["code"] == "paystack_void"


def test_unmatched_money_can_be_sent_back(owner_api, cashier_api, cashier_shift, manager, soda, fake_paystack):
    ref = paid_charge(cashier_api)
    url = f"/api/payments/momo/{ref}/refund/"
    assert cashier_api.post(url, {"reason": "Left", "approval_pin": ""}, format="json").status_code == 403
    assert owner_api.post(url, {"reason": ""}, format="json").status_code == 400
    r = owner_api.post(url, {"reason": "Customer left"}, format="json")
    assert r.status_code == 201 and r.data["amount"] == "24.00" and r.data["status"] == "pending"

    assert owner_api.get("/api/payments/momo/?unmatched=1").data == []
    assert owner_api.post(url, {"reason": "Again"}, format="json").status_code == 400
    # The money is on its way back, so it can no longer pay for a sale.
    used = cashier_api.post("/api/sales/checkout/", {"lines": [{"variant": soda.pk, "quantity": 2}],
                                                     "payments": [{"method": "momo", "amount": "24.00",
                                                                   "paystack_reference": ref}]}, format="json")
    assert used.status_code == 400 and used.data["code"] == "paystack_refunded"


def test_charge_on_a_sale_is_refunded_from_the_sale(owner_api, cashier_api, cashier_shift, manager, soda, fake_paystack):
    sale = paystack_sale(cashier_api, soda)
    ref = sale["payments"][0]["reference"]
    assert owner_api.post(f"/api/payments/momo/{ref}/refund/", {"reason": "x"}, format="json").status_code == 400


def test_list_is_for_report_viewers(owner_api, cashier_api, cashier_shift, manager, soda, fake_paystack):
    sale = paystack_sale(cashier_api, soda)
    refund(cashier_api, sale)
    assert cashier_api.get("/api/payments/refunds/").status_code == 403
    rows = owner_api.get("/api/payments/refunds/").data
    assert len(rows) == 1 and rows[0]["invoice_number"] == sale["invoice_number"]


def test_webhook_updates_refund_with_or_without_our_reference(cashier_api, cashier_shift, manager, soda, fake_paystack):
    sale = paystack_sale(cashier_api, soda)
    info = refund(cashier_api, sale).data["paystack"]
    client = APIClient()

    def send(event, **data):
        body = json.dumps({"event": event, "data": data}).encode()
        sig = hmac.new(b"sk_fake", body, hashlib.sha512).hexdigest()
        return client.post("/api/payments/paystack/webhook/", body, content_type="application/json",
                           HTTP_X_PAYSTACK_SIGNATURE=sig)

    row = PaystackRefund.objects.get()
    assert send("refund.processing", status="processing", refund_reference=None, amount="1200",
                transaction_reference=info["charge_reference"]).status_code == 200
    row.refresh_from_db()
    assert row.status == "processing"
    send("refund.processed", status="processed", refund_reference=info["reference"], amount="1200")
    row.refresh_from_db()
    assert row.status == "processed" and row.amount == D("12.00")
    # Webhooks can arrive late or out of order.
    send("refund.pending", status="pending", refund_reference=info["reference"], amount="1200")
    row.refresh_from_db()
    assert row.status == "processed"
