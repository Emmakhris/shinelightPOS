from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0")


def D(value) -> Decimal:
    if value is None or value == "":
        return ZERO
    return value if isinstance(value, Decimal) else Decimal(str(value))


def money(value) -> Decimal:
    """Round to pesewas (2 dp), half up, the way receipts are rounded."""
    return D(value).quantize(CENT, rounding=ROUND_HALF_UP)
