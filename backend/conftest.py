from decimal import Decimal

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.business.models import GHANA_DEFAULT_TAXES, Branch, BusinessProfile, TaxRate
from apps.catalog.models import Barcode, Product, Variant
from apps.inventory.services import change_stock
from apps.shifts.services import open_shift


@pytest.fixture(autouse=True)
def fast_password_hashing(settings):
    """Real password hashing is slow on purpose, and the tests create many users."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture(autouse=True)
def clear_cache():
    """Wrong-PIN counts and login throttles live in the cache and must not carry between tests."""
    cache.clear()


@pytest.fixture
def business(db):
    profile = BusinessProfile.get()
    profile.setup_complete = True
    profile.prices_include_tax = True
    profile.save()
    Branch.default()
    for t in GHANA_DEFAULT_TAXES:
        TaxRate.objects.create(**t)
    return profile


def make_user(username, role, pin=None):
    user = User(username=username, first_name=username.title(), role=role)
    user.set_password("secret123")
    if pin:
        user.set_pin(pin)
    user.save()
    return user


@pytest.fixture
def owner(business):
    return make_user("owner", Role.OWNER, "9999")


@pytest.fixture
def manager(business):
    return make_user("manager", Role.MANAGER, "1234")


@pytest.fixture
def cashier(business):
    return make_user("cashier", Role.CASHIER, "1111")


def api_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def cashier_api(cashier):
    return api_for(cashier)


@pytest.fixture
def owner_api(owner):
    return api_for(owner)


@pytest.fixture
def cashier_shift(cashier):
    return open_shift(cashier, Decimal("100.00"))


def make_item(name, price, cost="0", stock=10, tax_category="standard", barcode=None, **product_fields):
    product = Product.objects.create(name=name, tax_category=tax_category, **product_fields)
    variant = Variant.objects.create(product=product, price=Decimal(price), cost_price=Decimal(cost))
    if barcode:
        Barcode.objects.create(variant=variant, code=barcode)
    if product.track_stock and stock:
        change_stock(Branch.default(), variant, stock, "opening")
    return variant


@pytest.fixture
def soda(business):
    return make_item("Soda", "12.00", cost="7.00", stock=10, barcode="111")


@pytest.fixture
def rice(business):
    return make_item("Rice per kg", "18.00", cost="13.00", stock=20, tax_category="exempt", unit="kg")
