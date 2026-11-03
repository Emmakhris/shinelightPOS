"""
Paystack mobile money for Ghana (https://paystack.com/docs/payments/payment-channels/).

Flow: POST /charge with our own reference -> status "pay_offline" (customer approves on
their phone, within 180 seconds) or "send_otp" -> we poll GET /transaction/verify/:reference
until it is "success" or failed. A webhook (charge.success) can also confirm it when the
server is reachable from the internet.

Set PAYSTACK_SECRET_KEY in backend/.env. "sk_test_..." uses Paystack's test mode,
"sk_live_..." takes real money, and "sk_fake" runs a built-in simulator for training and tests.
"""
import hashlib
import hmac
import json
import re
import uuid
from datetime import timedelta
from decimal import Decimal
from urllib import error, request

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.business.models import BusinessProfile
from apps.common.exceptions import BusinessError
from apps.common.money import money

from .models import PAYSTACK_PROVIDERS, PaystackCharge

FAKE_KEY = "sk_fake"
APPROVAL_WINDOW = timedelta(seconds=180)  # set by the networks
MIN_CHECK_INTERVAL = timedelta(seconds=3)


class PaystackError(BusinessError):
    def __init__(self, message):
        super().__init__(message, code="paystack_error", http_status=502)


def secret_key():
    return getattr(settings, "PAYSTACK_SECRET_KEY", "") or ""


def mode():
    key = secret_key()
    if not key:
        return None
    if key == FAKE_KEY:
        return "simulated"
    return "live" if key.startswith("sk_live_") else "test"


def enabled():
    return mode() is not None


def _call(method, path, body=None):
    """Call the Paystack API and return the parsed JSON. Raises PaystackError on network problems."""
    if secret_key() == FAKE_KEY:
        return _fake_call(method, path, body)
    data = json.dumps(body).encode() if body is not None else None
    req = request.Request(
        f"{settings.PAYSTACK_BASE_URL}{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {secret_key()}", "Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode() or "{}")
    except error.HTTPError as exc:
        try:
            return json.loads(exc.read().decode() or "{}") | {"_http_status": exc.code}
        except ValueError:
            raise PaystackError(f"Paystack returned an error ({exc.code}).")
    except (error.URLError, TimeoutError, OSError):
        raise PaystackError(
            "Cannot reach Paystack. Check the internet connection, or record the MoMo payment manually."
        )


def normalise_phone(phone):
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("233") and len(digits) == 12:
        digits = "0" + digits[3:]
    if len(digits) != 10 or not digits.startswith("0"):
        raise BusinessError("Enter the customer's 10-digit MoMo number, e.g. 0241234567.")
    return digits


def _apply_status(charge, data, message=""):
    status = (data or {}).get("status")
    charge.raw = data or {}
    charge.paystack_id = str((data or {}).get("id") or charge.paystack_id)
    if (data or {}).get("display_text"):
        charge.display_text = data["display_text"][:255]
    if status == "success":
        paid = Decimal((data or {}).get("amount", 0)) / 100
        if money(paid) != charge.amount:
            # Never trust a success for a different amount than the till asked for.
            charge.status = PaystackCharge.Status.FAILED
            charge.message = f"Paystack confirmed {paid} instead of {charge.amount}. Check your Paystack dashboard."
        else:
            charge.status = PaystackCharge.Status.SUCCESS
            charge.paid_at = timezone.now()
            charge.message = (data or {}).get("gateway_response") or "Approved"
    elif status in ("pay_offline", "send_otp"):
        charge.status = status
    elif status in ("failed", "abandoned", "reversed"):
        charge.status = PaystackCharge.Status.FAILED
        charge.message = ((data or {}).get("gateway_response") or (data or {}).get("message") or message or
                          "The customer did not approve the payment.")[:255]
    return charge


def start_momo_charge(user, amount, phone, network):
    amount = money(amount)
    if amount <= 0:
        raise BusinessError("Enter an amount above zero.")
    if network not in PAYSTACK_PROVIDERS:
        raise BusinessError("Choose MTN, Telecel or AT.")
    phone = normalise_phone(phone)
    profile = BusinessProfile.get()
    if not profile.email:
        raise BusinessError("Add your business email in Settings first. Paystack sends payment receipts to it.")
    charge = PaystackCharge.objects.create(
        reference=f"SLP-{uuid.uuid4().hex[:20]}", amount=amount, phone=phone, network=network,
        currency=profile.currency_code or "GHS", created_by=user,
    )
    body = {
        "email": profile.email,
        "amount": str(int(amount * 100)),  # pesewas
        "currency": charge.currency,
        "reference": charge.reference,
        "mobile_money": {"phone": phone, "provider": PAYSTACK_PROVIDERS[network]},
        "metadata": {"source": "ShineLight POS", "cashier": user.display_name},
    }
    try:
        resp = _call("POST", "/charge", body)
    except PaystackError:
        # The request may still have reached Paystack; keep it pending so a status check can settle it.
        charge.message = "Could not confirm the prompt was sent. Checking…"
        charge.save()
        return charge
    if not resp.get("status") and not resp.get("data"):
        charge.status = PaystackCharge.Status.FAILED
        charge.message = (resp.get("message") or "Paystack refused the charge.")[:255]
    else:
        _apply_status(charge, resp.get("data"), resp.get("message", ""))
    charge.save()
    return charge


def check_charge(charge, force=False):
    """Ask Paystack for the latest status (unless it is already final or was checked a moment ago)."""
    now = timezone.now()
    if charge.status == PaystackCharge.Status.SUCCESS:
        return charge
    if not force and charge.last_checked_at and now - charge.last_checked_at < MIN_CHECK_INTERVAL:
        return charge
    resp = _call("GET", f"/transaction/verify/{charge.reference}")
    with transaction.atomic():
        charge = PaystackCharge.objects.select_for_update().get(pk=charge.pk)
        charge.last_checked_at = now
        data = resp.get("data") if resp.get("status") else None
        if data:
            status = data.get("status")
            if status in ("success", "failed", "abandoned", "reversed"):
                _apply_status(charge, data)
        elif resp.get("_http_status") in (400, 404) and now - charge.created_at > timedelta(minutes=5):
            charge.status = PaystackCharge.Status.FAILED
            charge.message = "Paystack has no record of this charge."
        if (charge.status in (PaystackCharge.Status.PAY_OFFLINE, PaystackCharge.Status.PENDING)
                and now - charge.created_at > APPROVAL_WINDOW + timedelta(seconds=60)):
            charge.status = PaystackCharge.Status.FAILED
            charge.message = "The customer did not approve in time."
        charge.save()
    return charge


def submit_otp(charge, otp):
    if charge.status != PaystackCharge.Status.SEND_OTP:
        raise BusinessError("This payment is not waiting for a code.")
    resp = _call("POST", "/charge/submit_otp", {"otp": str(otp).strip(), "reference": charge.reference})
    _apply_status(charge, resp.get("data"), resp.get("message", ""))
    if not resp.get("status") and charge.status == PaystackCharge.Status.SEND_OTP:
        charge.message = (resp.get("message") or "Code not accepted.")[:255]
    charge.save()
    return charge


def valid_signature(raw_body, signature):
    if not secret_key() or not signature:
        return False
    expected = hmac.new(secret_key().encode(), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)


def handle_webhook(event):
    if event.get("event") != "charge.success":
        return None
    data = event.get("data") or {}
    with transaction.atomic():
        charge = PaystackCharge.objects.select_for_update().filter(reference=data.get("reference")).first()
        if charge is None or charge.status == PaystackCharge.Status.SUCCESS:
            return charge
        _apply_status(charge, data)
        charge.save()
    return charge


# ---------------------------------------------------------------------------------------------
# Simulator (PAYSTACK_SECRET_KEY=sk_fake): no internet, no money. Numbers ending in 0000 are
# declined, numbers ending in 1111 ask for the code 123456, everything else is approved on
# the first status check.
# ---------------------------------------------------------------------------------------------
_FAKE = {}


def _fake_call(method, path, body):
    if method == "POST" and path == "/charge":
        phone = body["mobile_money"]["phone"]
        ref = body["reference"]
        status = "send_otp" if phone.endswith("1111") else "pay_offline"
        _FAKE[ref] = {"phone": phone, "amount": int(body["amount"]), "status": status, "checks": 0}
        text = "Enter the code sent to the customer" if status == "send_otp" else \
            "Please complete authorization process on your mobile phone"
        return {"status": True, "message": "Charge attempted",
                "data": {"reference": ref, "status": status, "display_text": text}}
    if method == "POST" and path == "/charge/submit_otp":
        fake = _FAKE.get(body["reference"])
        if not fake or body["otp"] != "123456":
            return {"status": False, "message": "Invalid code", "data": {"status": "send_otp"}}
        fake["status"] = "pay_offline"
        return {"status": True, "message": "Charge attempted",
                "data": {"reference": body["reference"], "status": "pay_offline",
                         "display_text": "Please complete authorization process on your mobile phone"}}
    if method == "GET" and path.startswith("/transaction/verify/"):
        ref = path.rsplit("/", 1)[1]
        fake = _FAKE.get(ref)
        if not fake:
            return {"status": False, "message": "Transaction reference not found", "_http_status": 400}
        fake["checks"] += 1
        if fake["status"] == "send_otp":
            return {"status": True, "data": {"reference": ref, "status": "ongoing", "amount": fake["amount"]}}
        if fake["phone"].endswith("0000"):
            return {"status": True, "data": {"reference": ref, "status": "failed", "amount": fake["amount"],
                                              "gateway_response": "Declined by customer"}}
        return {"status": True, "data": {"id": 1000 + len(_FAKE), "reference": ref, "status": "success",
                                          "amount": fake["amount"], "gateway_response": "Approved"}}
    return {"status": False, "message": "Not simulated"}
