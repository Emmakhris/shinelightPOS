import threading
from unittest import mock

from apps.accounts.models import Role, User
from apps.accounts.services import find_approver
from conftest import make_user


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
