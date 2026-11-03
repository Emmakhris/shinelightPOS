"""
Tax engine. Works per sale line so receipts, refunds and the tax report all agree.

Prices can be tax-inclusive (the shelf price already contains VAT and levies) or
tax-exclusive (taxes are added at the till). Each standard-rated line gets every active
TaxRate in order; a compound rate is charged on the value plus the taxes before it.
"""
from dataclasses import dataclass, field
from decimal import Decimal

from apps.common.money import ZERO, money

from .models import TaxCategory, TaxRate


@dataclass
class TaxLine:
    code: str
    name: str
    rate: Decimal
    amount: Decimal


@dataclass
class TaxResult:
    net: Decimal
    taxes: list = field(default_factory=list)

    @property
    def tax_total(self):
        return sum((t.amount for t in self.taxes), ZERO)

    @property
    def gross(self):
        return self.net + self.tax_total


def active_rates():
    return list(TaxRate.objects.filter(is_active=True))


def _taxes_on(net, rates, rounded=True):
    taxes = []
    running = ZERO
    for r in rates:
        base = net + (running if r.compound else ZERO)
        amount = base * r.rate / Decimal(100)
        if rounded:
            amount = money(amount)
        running += amount
        taxes.append(TaxLine(r.code, r.name, r.rate, amount))
    return taxes


def compute_tax(amount, tax_category, rates, inclusive):
    """amount is the line value after discounts: gross if inclusive, net if exclusive."""
    amount = money(amount)
    if tax_category != TaxCategory.STANDARD or not rates:
        return TaxResult(net=amount)
    if not inclusive:
        return TaxResult(net=amount, taxes=_taxes_on(amount, rates))
    # Work out how much one cedi of net value grows to, then back the net out of the gross.
    multiplier = Decimal(1) + sum(t.amount for t in _taxes_on(Decimal(1), rates, rounded=False))
    taxes = _taxes_on(amount / multiplier, rates)
    # The net absorbs the rounding so net + taxes always equals the price the customer saw.
    net = amount - sum((t.amount for t in taxes), ZERO)
    return TaxResult(net=net, taxes=taxes)
