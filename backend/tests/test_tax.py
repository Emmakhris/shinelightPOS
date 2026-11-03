from decimal import Decimal as D
from types import SimpleNamespace

from apps.business.tax import compute_tax


def rate(code, value, compound=False):
    return SimpleNamespace(code=code, name=code, rate=D(value), compound=compound)


FLAT = [rate("NHIL", "2.5"), rate("GETFUND", "2.5"), rate("VAT", "15")]
COMPOUND = [rate("NHIL", "2.5"), rate("GETFUND", "2.5"), rate("VAT", "15", compound=True)]


def amounts(result):
    return {t.code: t.amount for t in result.taxes}


def test_exclusive_flat_rates_add_twenty_percent():
    r = compute_tax(D("100.00"), "standard", FLAT, inclusive=False)
    assert amounts(r) == {"NHIL": D("2.50"), "GETFUND": D("2.50"), "VAT": D("15.00")}
    assert r.gross == D("120.00")


def test_inclusive_backs_tax_out_of_shelf_price():
    r = compute_tax(D("12.00"), "standard", FLAT, inclusive=True)
    assert r.net == D("10.00")
    assert r.tax_total == D("2.00")
    assert r.gross == D("12.00")


def test_compound_vat_is_charged_on_value_plus_levies():
    r = compute_tax(D("100.00"), "standard", COMPOUND, inclusive=False)
    assert amounts(r)["VAT"] == D("15.75")
    assert r.gross == D("120.75")
    back = compute_tax(D("120.75"), "standard", COMPOUND, inclusive=True)
    assert back.net == D("100.00")


def test_inclusive_rounding_always_adds_back_to_the_price():
    for price in ["9.99", "0.05", "1.01", "333.33", "7.77"]:
        r = compute_tax(D(price), "standard", COMPOUND, inclusive=True)
        assert r.net + r.tax_total == D(price)


def test_exempt_and_zero_rated_have_no_tax():
    for cat in ["exempt", "zero"]:
        r = compute_tax(D("50.00"), cat, FLAT, inclusive=True)
        assert r.taxes == [] and r.net == D("50.00")
