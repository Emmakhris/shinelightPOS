"""
Cart pricing. The same function prices the live cart preview (/sales/quote/) and the final
sale, so the till never shows a total the server will not charge.
"""
from dataclasses import dataclass, field
from decimal import Decimal

from apps.business.tax import compute_tax
from apps.catalog.models import Modifier, Variant
from apps.common.exceptions import BusinessError
from apps.common.money import ZERO, D, money


@dataclass
class CartLine:
    variant: Variant
    quantity: Decimal
    modifiers: list = field(default_factory=list)  # Modifier objects
    discount_type: str = "amount"  # "amount" (per line, in cedis) or "percent"
    discount_value: Decimal = ZERO
    unit_price: Decimal | None = None  # price override
    note: str = ""


@dataclass
class PricedLine:
    source: CartLine
    name: str
    unit_price: Decimal
    gross: Decimal  # unit_price x qty
    line_discount: Decimal
    cart_discount: Decimal = ZERO
    net_amount: Decimal = ZERO
    tax_amount: Decimal = ZERO
    total: Decimal = ZERO
    taxes: list = field(default_factory=list)

    @property
    def discount(self):
        return self.line_discount + self.cart_discount

    @property
    def price_overridden(self):
        return self.source.unit_price is not None and money(self.source.unit_price) != self.list_unit_price

    @property
    def list_unit_price(self):
        return money(self.source.variant.price + sum((m.price for m in self.source.modifiers), ZERO))


@dataclass
class PricedCart:
    lines: list
    subtotal: Decimal
    discount_total: Decimal
    tax_total: Decimal
    total: Decimal
    taxes: dict  # code -> {"name", "rate", "amount"}

    @property
    def discount_percent(self):
        return (self.discount_total / self.subtotal * 100) if self.subtotal else ZERO

    def as_dict(self):
        return {
            "subtotal": str(self.subtotal),
            "discount_total": str(self.discount_total),
            "tax_total": str(self.tax_total),
            "total": str(self.total),
            "taxes": [{"code": c, **{k: str(v) for k, v in t.items()}} for c, t in self.taxes.items()],
            "lines": [
                {
                    "variant": pl.source.variant.pk,
                    "name": pl.name,
                    "quantity": str(pl.source.quantity),
                    "unit_price": str(pl.unit_price),
                    "discount": str(pl.discount),
                    "net_amount": str(pl.net_amount),
                    "tax_amount": str(pl.tax_amount),
                    "total": str(pl.total),
                }
                for pl in self.lines
            ],
        }


def build_cart_lines(raw_lines):
    """Turn validated request data into CartLine objects, checking modifiers and quantities."""
    variant_ids = [line["variant"] for line in raw_lines]
    variants = {
        v.pk: v
        for v in Variant.objects.filter(pk__in=variant_ids).select_related("product").prefetch_related(
            "product__modifier_groups"
        )
    }
    modifier_ids = {m for line in raw_lines for m in line.get("modifiers", [])}
    modifiers = {m.pk: m for m in Modifier.objects.filter(pk__in=modifier_ids).select_related("group")}
    lines = []
    for raw in raw_lines:
        variant = variants.get(raw["variant"])
        if variant is None or not variant.is_active or not variant.product.is_active:
            raise BusinessError("An item in the cart is no longer for sale.")
        qty = D(raw["quantity"])
        if qty <= 0:
            raise BusinessError(f"Quantity for {variant.full_name} must be above zero.")
        if not variant.product.allows_fraction and qty != qty.to_integral_value():
            raise BusinessError(f"{variant.full_name} is sold in whole units.")
        mods = []
        allowed_groups = {g.pk: g for g in variant.product.modifier_groups.all()}
        for mid in raw.get("modifiers", []):
            mod = modifiers.get(mid)
            if mod is None or mod.group_id not in allowed_groups:
                raise BusinessError(f"That option is not available for {variant.full_name}.")
            mods.append(mod)
        for group in allowed_groups.values():
            chosen = sum(1 for m in mods if m.group_id == group.pk)
            if chosen < group.min_select:
                raise BusinessError(f"Choose {group.name} for {variant.full_name}.")
            if group.max_select and chosen > group.max_select:
                raise BusinessError(f"Too many {group.name} options for {variant.full_name}.")
        lines.append(CartLine(
            variant=variant, quantity=qty, modifiers=mods,
            discount_type=raw.get("discount_type") or "amount",
            discount_value=D(raw.get("discount_value")),
            unit_price=None if raw.get("unit_price") in (None, "") else D(raw["unit_price"]),
            note=raw.get("note") or "",
        ))
    return lines


def _clamp(value, low, high):
    return max(low, min(value, high))


def price_cart(lines, rates, inclusive, cart_discount_type="amount", cart_discount_value=ZERO):
    if not lines:
        raise BusinessError("The cart is empty.")
    priced = []
    for line in lines:
        list_price = money(line.variant.price + sum((m.price for m in line.modifiers), ZERO))
        unit_price = money(line.unit_price) if line.unit_price is not None else list_price
        if unit_price < 0:
            raise BusinessError("Price cannot be negative.")
        gross = money(unit_price * line.quantity)
        if line.discount_type == "percent":
            line_discount = money(gross * _clamp(line.discount_value, ZERO, Decimal(100)) / 100)
        else:
            line_discount = money(_clamp(line.discount_value, ZERO, gross))
        priced.append(PricedLine(
            source=line, name=line.variant.full_name, unit_price=unit_price, gross=gross,
            line_discount=line_discount,
        ))

    # Spread the cart discount over the lines in proportion to their value so each line's tax is right.
    after_line = sum((p.gross - p.line_discount for p in priced), ZERO)
    if cart_discount_type == "percent":
        cart_discount = money(after_line * _clamp(D(cart_discount_value), ZERO, Decimal(100)) / 100)
    else:
        cart_discount = money(_clamp(D(cart_discount_value), ZERO, after_line))
    remaining = cart_discount
    for i, p in enumerate(priced):
        base = p.gross - p.line_discount
        if i == len(priced) - 1:
            share = remaining
        else:
            share = money(cart_discount * base / after_line) if after_line else ZERO
        share = min(share, base, remaining)
        p.cart_discount = share
        remaining -= share

    taxes = {}
    for p in priced:
        amount = p.gross - p.discount
        result = compute_tax(amount, p.source.variant.product.tax_category, rates, inclusive)
        p.net_amount = result.net
        p.tax_amount = result.tax_total
        p.total = result.gross
        p.taxes = result.taxes
        for t in result.taxes:
            entry = taxes.setdefault(t.code, {"name": t.name, "rate": t.rate, "amount": ZERO})
            entry["amount"] += t.amount

    subtotal = sum((p.gross for p in priced), ZERO)
    discount_total = sum((p.discount for p in priced), ZERO)
    tax_total = sum((p.tax_amount for p in priced), ZERO)
    total = sum((p.total for p in priced), ZERO)
    return PricedCart(priced, subtotal, discount_total, tax_total, total, taxes)
