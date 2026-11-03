import hashlib
import hmac
import json
from decimal import Decimal as D
from unittest import mock

import pytest
from rest_framework.test import APIClient

from apps.payments import paystack
from apps.payments.models import PaystackCharge
from apps.sales.models import Payment

pytestmark = pytest.mark.django_db


@pytest.fixture
def fake_paystack(settings, business):
    settings.PAYSTACK_SECRET_KEY = "sk_fake"
    business.email = "shop@example.com"
    business.save()
    return settings


def start(api, amount="24.00", phone="0241234567", network="mtn"):
    return api.post("/api/payments/momo/", {"amount": amount, "phone": phone, "network": network}, format="json")


def checkout(api, variant, qty, payments):
    return api.post("/api/sales/checkout/", {"lines": [{"variant": variant.pk, "quantity": qty}],
                                             "payments": payments}, format="json")


def test_settings_report_the_paystack_mode(owner_api, fake_paystack):
    assert owner_api.get("/api/settings/").data["paystack_mode"] == "simulated"
    fake_paystack.PAYSTACK_SECRET_KEY = "sk_test_abc"
    assert owner_api.get("/api/settings/").data["paystack_mode"] == "test"
    fake_paystack.PAYSTACK_SECRET_KEY = ""
    assert owner_api.get("/api/settings/").data["paystack_mode"] is None
    assert start(owner_api).status_code == 400  # not set up


def test_needs_business_email(cashier_api, fake_paystack, business):
    business.email = ""
    business.save()
    r = start(cashier_api)
    assert r.status_code == 400 and "email" in r.data["detail"]


def test_prompt_confirm_and_pay_for_a_sale(cashier_api, cashier_shift, soda, fake_paystack):
    r = start(cashier_api, phone="+233 24 123 4567")
    assert r.status_code == 201, r.data
    assert r.data["status"] == "pay_offline" and r.data["phone"] == "0241234567"
    ref = r.data["reference"]

    # Not yet confirmed by Paystack: the sale must be refused.
    early = checkout(cashier_api, soda, 2, [{"method": "momo", "amount": "24.00", "paystack_reference": ref}])
    assert early.status_code == 400 and early.data["code"] == "paystack_unconfirmed"

    status = cashier_api.get(f"/api/payments/momo/{ref}/?force=1").data
    assert status["status"] == "success"

    sale = checkout(cashier_api, soda, 2, [{"method": "momo", "amount": "24.00", "paystack_reference": ref}])
    assert sale.status_code == 201, sale.data
    payment = sale.data["payments"][0]
    assert payment["reference"] == ref and payment["momo_network"] == "mtn"
    assert PaystackCharge.objects.get(reference=ref).payment_id == payment["id"]

    again = checkout(cashier_api, soda, 2, [{"method": "momo", "amount": "24.00", "paystack_reference": ref}])
    assert again.status_code == 400 and again.data["code"] == "paystack_used"


def test_amount_must_match_and_method_must_be_momo(cashier_api, cashier_shift, soda, fake_paystack):
    ref = start(cashier_api, amount="10.00").data["reference"]
    cashier_api.get(f"/api/payments/momo/{ref}/?force=1")
    wrong = checkout(cashier_api, soda, 1, [{"method": "momo", "amount": "12.00", "paystack_reference": ref}])
    assert wrong.status_code == 400
    card = checkout(cashier_api, soda, 1, [{"method": "card", "amount": "10.00", "paystack_reference": ref},
                                          {"method": "cash", "amount": "2.00"}])
    assert card.status_code == 400
    ok = checkout(cashier_api, soda, 1, [{"method": "momo", "amount": "10.00", "paystack_reference": ref},
                                        {"method": "cash", "amount": "2.00"}])
    assert ok.status_code == 201, ok.data


def test_declined_by_customer(cashier_api, fake_paystack):
    ref = start(cashier_api, phone="0240000000").data["reference"]
    r = cashier_api.get(f"/api/payments/momo/{ref}/?force=1").data
    assert r["status"] == "failed" and "Declined" in r["message"]


def test_code_required(cashier_api, fake_paystack):
    r = start(cashier_api, phone="0201111111", network="telecel").data
    assert r["status"] == "send_otp"
    bad = cashier_api.post(f"/api/payments/momo/{r['reference']}/otp/", {"otp": "000000"}).data
    assert bad["status"] == "send_otp" and bad["message"]
    good = cashier_api.post(f"/api/payments/momo/{r['reference']}/otp/", {"otp": "123456"}).data
    assert good["status"] == "pay_offline"
    assert cashier_api.get(f"/api/payments/momo/{r['reference']}/?force=1").data["status"] == "success"


def test_cancel_then_approved_later_shows_as_unmatched(owner_api, cashier_api, fake_paystack):
    ref = start(cashier_api).data["reference"]
    assert cashier_api.post(f"/api/payments/momo/{ref}/cancel/").data["status"] == "abandoned"
    # The customer approved anyway: a recheck picks it up and the owner sees unmatched money.
    assert owner_api.get(f"/api/payments/momo/{ref}/?force=1").data["status"] == "success"
    unmatched = owner_api.get("/api/payments/momo/?unmatched=1").data
    assert [c["reference"] for c in unmatched] == [ref]
    assert cashier_api.post(f"/api/payments/momo/{ref}/cancel/").status_code == 400


def test_bad_phone_numbers_are_rejected(cashier_api, fake_paystack):
    assert start(cashier_api, phone="12345").status_code == 400
    assert start(cashier_api, network="vodafone").status_code == 400


def test_real_mode_request_and_amount_check(settings, cashier_api, business):
    settings.PAYSTACK_SECRET_KEY = "sk_test_x"
    business.email = "shop@example.com"
    business.save()
    calls = []

    def fake_http(method, path, body=None):
        calls.append((method, path, body))
        if path == "/charge":
            return {"status": True, "data": {"status": "pay_offline", "display_text": "Approve on phone"}}
        # Paystack reports success but for a different amount than we asked for.
        return {"status": True, "data": {"status": "success", "amount": 100, "gateway_response": "Approved"}}

    with mock.patch.object(paystack, "_call", side_effect=fake_http):
        r = start(cashier_api, amount="24.50", phone="0201234567", network="telecel").data
        body = calls[0][2]
        assert body["amount"] == "2450" and body["currency"] == "GHS"
        assert body["mobile_money"] == {"phone": "0201234567", "provider": "vod"}
        assert body["reference"] == r["reference"] and body["email"] == "shop@example.com"
        checked = cashier_api.get(f"/api/payments/momo/{r['reference']}/?force=1").data
    assert calls[1][1] == f"/transaction/verify/{r['reference']}"
    assert checked["status"] == "failed" and "instead of" in checked["message"]


def test_unreachable_paystack_keeps_charge_pending(settings, cashier_api, business):
    settings.PAYSTACK_SECRET_KEY = "sk_test_x"
    business.email = "shop@example.com"
    business.save()
    with mock.patch.object(paystack, "_call", side_effect=paystack.PaystackError("offline")):
        r = start(cashier_api)
    assert r.status_code == 201 and r.data["status"] == "pending"


def test_webhook_signature(settings, cashier_api, fake_paystack):
    ref = start(cashier_api).data["reference"]
    body = json.dumps({"event": "charge.success",
                       "data": {"reference": ref, "status": "success", "amount": 2400}}).encode()
    client = APIClient()
    bad = client.post("/api/payments/paystack/webhook/", body, content_type="application/json",
                      HTTP_X_PAYSTACK_SIGNATURE="nope")
    assert bad.status_code == 401
    sig = hmac.new(b"sk_fake", body, hashlib.sha512).hexdigest()
    ok = client.post("/api/payments/paystack/webhook/", body, content_type="application/json",
                     HTTP_X_PAYSTACK_SIGNATURE=sig)
    assert ok.status_code == 200
    charge = PaystackCharge.objects.get(reference=ref)
    assert charge.status == "success" and charge.amount == D("24.00")
    assert not Payment.objects.exists()
