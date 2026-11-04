import threading
from unittest import mock

from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import AuditLog, Role, User
from apps.accounts.services import PIN_MAX_TRIES, find_approver
from conftest import api_for, make_user


def void(api, sale, pin):
    return api.post(f"/api/sales/{sale['id']}/void/", {"reason": "Mistake", "approval_pin": pin}, format="json")


def cash_sale(api, variant):
    r = api.post("/api/sales/checkout/", {"lines": [{"variant": variant.pk, "quantity": 1}],
                                          "payments": [{"method": "cash", "amount": "100"}]}, format="json")
    assert r.status_code == 201, r.data
    return r.data


def lock_out(api, sale):
    for _ in range(PIN_MAX_TRIES - 1):
        assert void(api, sale, "0000").data["code"] == "approval_required"
    return void(api, sale, "0000")


def test_wrong_approval_pins_lock_the_user_out(cashier_api, cashier_shift, manager, soda):
    sale = cash_sale(cashier_api, soda)
    locked = lock_out(cashier_api, sale)
    assert locked.status_code == 429 and locked.data["code"] == "pin_locked"
    # Void runs in a database transaction that rolls back: the lockout must still be on record.
    entry = AuditLog.objects.get(action="pin_locked")
    assert entry.user.username == "cashier" and entry.details["kind"] == "approval"
    # While locked, even the right PIN is refused and is not checked.
    with mock.patch.object(User, "check_pin", side_effect=AssertionError):
        assert void(cashier_api, sale, "1234").status_code == 429
    assert AuditLog.objects.filter(action="pin_locked").count() == 1


def test_lockout_ends_after_the_wait(cashier_api, cashier_shift, manager, soda):
    sale = cash_sale(cashier_api, soda)
    lock_out(cashier_api, sale)
    cache.clear()  # what the end of the 15 minutes does
    assert void(cashier_api, sale, "1234").status_code == 200


def test_right_pin_resets_the_count(cashier_api, cashier_shift, manager, soda):
    sale = cash_sale(cashier_api, soda)
    for _ in range(PIN_MAX_TRIES - 1):
        void(cashier_api, sale, "0000")
    verify = cashier_api.post("/api/auth/verify-approval/", {"pin": "1234"}, format="json")
    assert verify.status_code == 200
    for _ in range(PIN_MAX_TRIES - 1):
        assert void(cashier_api, sale, "0000").status_code == 403


def test_verify_approval_counts_too_and_blank_pins_do_not(cashier_api, manager):
    for _ in range(PIN_MAX_TRIES * 2):
        assert cashier_api.post("/api/auth/verify-approval/", {"pin": ""}, format="json").status_code == 403
    for _ in range(PIN_MAX_TRIES - 1):
        assert cashier_api.post("/api/auth/verify-approval/", {"pin": "0000"}, format="json").status_code == 403
    assert cashier_api.post("/api/auth/verify-approval/", {"pin": "0000"}, format="json").status_code == 429


def test_one_locked_user_does_not_affect_others(cashier_api, cashier_shift, manager, soda, business):
    sale = cash_sale(cashier_api, soda)
    lock_out(cashier_api, sale)
    other = api_for(make_user("cashier2", Role.CASHIER, "2222"))
    assert other.post("/api/auth/verify-approval/", {"pin": "1234"}, format="json").status_code == 200
    # A manager signed in at the till needs no PIN.
    assert void(api_for(manager), sale, "").status_code == 200


def test_pin_sign_in_locks_that_person_but_not_their_password(manager):
    client = APIClient()

    def sign_in(pin):
        return client.post("/api/auth/pin-login/", {"user_id": manager.pk, "pin": pin}, format="json")

    for _ in range(PIN_MAX_TRIES - 1):
        assert sign_in("0000").status_code == 401
    locked = sign_in("0000")
    assert locked.status_code == 429 and "password" in locked.data["detail"]
    assert sign_in("1234").status_code == 429
    entry = AuditLog.objects.get(action="pin_locked")
    assert entry.user == manager and entry.details["kind"] == "sign_in"
    assert client.post("/api/auth/login/", {"username": "manager", "password": "secret123"},
                       format="json").status_code == 200


def test_tries_are_counted_before_checking(cashier, cashier_api, manager):
    """Requests sent at the same time must not all get a check before the first one finishes."""
    tries = []

    def check_pin(self, pin):
        # The count already includes this try while the slow check is still running.
        tries.append(cache.get(f"pin-tries:approval:{cashier.pk}"))
        return False

    with mock.patch.object(User, "check_pin", check_pin):
        cashier_api.post("/api/auth/verify-approval/", {"pin": "0000"}, format="json")
    assert tries == [1]


def test_finds_the_manager_whose_pin_matches(owner, manager):
    assert find_approver("1234") == manager
    assert find_approver("9999") == owner
    assert find_approver("0000") is None
    assert find_approver("") is None


def test_only_active_owners_and_managers_can_approve(manager, business):
    make_user("cashier2", Role.CASHIER, "5555")
    assert find_approver("5555") is None
    manager.is_active = False
    manager.save()
    assert find_approver("1234") is None


def test_no_managers_with_a_pin(business):
    make_user("cashier2", Role.CASHIER, "5555")
    assert find_approver("5555") is None


def test_pins_are_checked_at_the_same_time(owner, manager):
    """If the checks ran one after another, the first would wait here until the barrier timed out."""
    barrier = threading.Barrier(2, timeout=10)

    def check_pin(self, pin):
        barrier.wait()
        return self.username == "manager"

    with mock.patch.object(User, "check_pin", check_pin):
        assert find_approver("1234") == manager
