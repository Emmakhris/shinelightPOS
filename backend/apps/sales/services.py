from decimal import ROUND_DOWN

from django.db import transaction
from django.utils import timezone

from apps.accounts.services import audit, require_permission_or_approval
from apps.business.models import Branch, BusinessProfile
from apps.business.services import next_document_number
from apps.business.tax import active_rates
from apps.common.exceptions import BusinessError
from apps.common.money import ZERO, D, money
from apps.customers.models import Customer, CustomerTransaction
from apps.inventory.services import change_stock
from apps.shifts.services import require_shift

from .models import OrderType, Payment, PaymentMethod, Refund, RefundLine, Sale, SaleLine, SaleTax
from .pricing import build_cart_lines, price_cart

NON_CHANGE_METHODS = {PaymentMethod.MOMO, PaymentMethod.CARD, PaymentMethod.BANK,
                      PaymentMethod.CREDIT, PaymentMethod.POINTS}


def quote(data):
    profile = BusinessProfile.get()
    lines = build_cart_lines(data["lines"])
    return price_cart(
        lines, active_rates(), profile.prices_include_tax,
        data.get("discount_type") or "amount", data.get("discount_value") or ZERO,
    )


def _check_approvals(user, cart, profile, approval_pin):
    """Price overrides and big discounts need the right role or a manager PIN."""
    approver = None
    if any(p.price_overridden for p in cart.lines):
        approver = require_permission_or_approval(
            user, "price_override", approval_pin, "Changing a price needs manager approval."
        ) or approver
    if cart.discount_total and cart.discount_percent > profile.discount_approval_percent:
        approver = require_permission_or_approval(
            user, "discount_override", approval_pin,
            f"Discounts above {profile.discount_approval_percent.normalize():f}% need manager approval.",
        ) or approver
    return approver


def _validate_payments(payments, total, customer, profile):
    if not payments:
        raise BusinessError("Add a payment.")
    paid = sum((money(p["amount"]) for p in payments), ZERO)
    non_cash = sum((money(p["amount"]) for p in payments if p["method"] in NON_CHANGE_METHODS), ZERO)
    if any(money(p["amount"]) <= 0 for p in payments):
        raise BusinessError("Payment amounts must be above zero.")
    if paid < total:
        raise BusinessError(f"Payment is short by {money(total - paid)}.", code="payment_short")
    if non_cash > total:
        raise BusinessError("Only cash can be more than the amount due (to give change).")
    credit = sum((money(p["amount"]) for p in payments if p["method"] == PaymentMethod.CREDIT), ZERO)
    points_cash = sum((money(p["amount"]) for p in payments if p["method"] == PaymentMethod.POINTS), ZERO)
    if (credit or points_cash) and customer is None:
        raise BusinessError("Choose a customer to pay on credit or with points.")
    if credit and customer.balance + credit > customer.credit_limit:
        available = max(customer.credit_limit - customer.balance, ZERO)
        raise BusinessError(f"{customer.name} has only {available} credit available.", code="credit_limit")
    points_needed = ZERO
    if points_cash:
        if not profile.loyalty_enabled or not profile.loyalty_point_value:
            raise BusinessError("Loyalty points are turned off.")
        points_needed = (points_cash / profile.loyalty_point_value).quantize(D("0.01"))
        if points_needed > customer.loyalty_points:
            raise BusinessError(f"{customer.name} has only {customer.loyalty_points} points.", code="points")
    return paid, credit, points_needed


def _confirmed_paystack_charge(p):
    """A MoMo payment taken through Paystack counts only if the server itself saw it succeed."""
    from apps.payments.models import PaystackCharge

    charge = PaystackCharge.objects.select_for_update().filter(reference=p["paystack_reference"]).first()
    if charge is None or p["method"] != PaymentMethod.MOMO:
        raise BusinessError("Unknown Paystack payment.")
    if charge.status != PaystackCharge.Status.SUCCESS:
        raise BusinessError("That MoMo payment has not been confirmed by Paystack.", code="paystack_unconfirmed")
    if charge.payment_id:
        raise BusinessError("That MoMo payment is already used on another sale.", code="paystack_used")
    if charge.refunds.exists():
        raise BusinessError("That MoMo payment was refunded to the customer.", code="paystack_refunded")
    if charge.amount != money(p["amount"]):
        raise BusinessError("The MoMo payment amount does not match.")
    return charge


@transaction.atomic
def create_sale(user, data, order_type=OrderType.RETAIL, table_name=""):
    """
    data: lines, discount_type, discount_value, payments, customer (id), note, approval_pin.
    Everything (stock, invoice number, customer balance, points) happens in one transaction.
    """
    profile = BusinessProfile.get()
    branch = Branch.default()
    shift = require_shift(user)
    cart = quote(data)
    approver = _check_approvals(user, cart, profile, data.get("approval_pin"))

    customer = None
    if data.get("customer"):
        customer = Customer.objects.select_for_update().filter(pk=data["customer"], is_active=True).first()
        if customer is None:
            raise BusinessError("Customer not found.")

    payments = data.get("payments") or []
    paid, credit, points_needed = _validate_payments(payments, cart.total, customer, profile)
    points_cash = sum((money(p["amount"]) for p in payments if p["method"] == PaymentMethod.POINTS), ZERO)

    sale = Sale.objects.create(
        branch=branch, invoice_number=next_document_number(branch, "invoice"), order_type=order_type,
        table_name=table_name, customer=customer, cashier=user, shift=shift,
        prices_include_tax=profile.prices_include_tax, subtotal=cart.subtotal,
        discount_total=cart.discount_total, tax_total=cart.tax_total, total=cart.total, paid_total=paid,
        change_due=paid - cart.total, note=(data.get("note") or "")[:255], approved_by=approver,
        points_redeemed=points_needed,
    )

    cost_total = ZERO
    for p in cart.lines:
        variant = p.source.variant
        product = variant.product
        SaleLine.objects.create(
            sale=sale, variant=variant, name=p.name, sku=variant.sku or "", quantity=p.source.quantity,
            unit_price=p.unit_price, discount=p.discount, net_amount=p.net_amount, tax_amount=p.tax_amount,
            total=p.total, unit_cost=variant.cost_price, tax_category=product.tax_category,
            track_stock=product.track_stock, note=p.source.note[:255],
            modifiers=[{"id": m.pk, "name": m.name, "price": str(m.price)} for m in p.source.modifiers],
        )
        cost_total += money(variant.cost_price * p.source.quantity)
        if product.track_stock:
            change_stock(branch, variant, -p.source.quantity, "sale", user=user,
                         reference=sale.invoice_number, enforce_available=True)
    for code, t in cart.taxes.items():
        SaleTax.objects.create(sale=sale, code=code, name=t["name"], rate=t["rate"], amount=t["amount"])
    for p in payments:
        charge = _confirmed_paystack_charge(p) if p.get("paystack_reference") else None
        payment = Payment.objects.create(
            sale=sale, method=p["method"], amount=money(p["amount"]),
            momo_network=charge.network if charge else (p.get("momo_network") or ""),
            reference=charge.reference if charge else (p.get("reference") or ""),
        )
        if charge:
            charge.payment = payment
            charge.save(update_fields=["payment", "updated_at"])

    if customer:
        if credit:
            customer.balance += credit
            CustomerTransaction.objects.create(
                customer=customer, kind=CustomerTransaction.Kind.CREDIT_SALE, amount=credit, sale=sale, user=user
            )
        if points_needed:
            customer.loyalty_points -= points_needed
            CustomerTransaction.objects.create(
                customer=customer, kind=CustomerTransaction.Kind.POINTS_REDEEMED, points=-points_needed,
                sale=sale, user=user,
            )
        if profile.loyalty_enabled:
            earn_on = cart.total - points_cash
            earned = (earn_on * profile.loyalty_points_per_cedi).quantize(D("0.01"), rounding=ROUND_DOWN)
            if earned > 0:
                customer.loyalty_points += earned
                sale.points_earned = earned
                CustomerTransaction.objects.create(
                    customer=customer, kind=CustomerTransaction.Kind.POINTS_EARNED, points=earned, sale=sale, user=user
                )
        customer.save(update_fields=["balance", "loyalty_points"])

    sale.cost_total = cost_total
    sale.save(update_fields=["cost_total", "points_earned"])
    if approver:
        audit("sale_approved", user, "sale", sale.pk, approved_by=approver, invoice=sale.invoice_number,
              discount=str(cart.discount_total), price_override=any(p.price_overridden for p in cart.lines))
    return sale


def _reverse_customer_effects(sale, fraction, user, refund_method=None, refund_amount=ZERO):
    """Take back a share of earned points; put refunded credit back on the customer's balance."""
    customer = sale.customer
    if not customer:
        return
    customer = Customer.objects.select_for_update().get(pk=customer.pk)
    if sale.points_earned:
        points = min((sale.points_earned * fraction).quantize(D("0.01")), customer.loyalty_points)
        if points > 0:
            customer.loyalty_points -= points
            CustomerTransaction.objects.create(
                customer=customer, kind=CustomerTransaction.Kind.POINTS_REVERSED, points=-points, sale=sale, user=user
            )
    if refund_method == PaymentMethod.CREDIT and refund_amount:
        reduce_by = min(refund_amount, customer.balance)
        customer.balance -= reduce_by
        CustomerTransaction.objects.create(
            customer=customer, kind=CustomerTransaction.Kind.CREDIT_REFUND, amount=-reduce_by, sale=sale, user=user
        )
    customer.save(update_fields=["balance", "loyalty_points"])


def _create_paystack_refund(user, sale, refund, approver):
    """Saved here with the sale refund. The view sends it to Paystack after the transaction commits."""
    from apps.payments import paystack
    from apps.payments.models import PaystackCharge, PaystackRefund

    if not paystack.enabled():
        raise BusinessError("Paystack is not set up. Choose another way to refund.")
    charges = list(PaystackCharge.objects.select_for_update().filter(payment__sale=sale).order_by("created_at"))
    if not charges:
        raise BusinessError("This sale was not paid through Paystack. Choose another way to refund.")
    for charge in charges:
        if charge.refundable_amount >= refund.amount:
            refund.reference = paystack.new_refund_reference()
            refund.save(update_fields=["reference"])
            return PaystackRefund.objects.create(
                reference=refund.reference, charge=charge, sale_refund=refund, amount=refund.amount,
                reason=refund.reason, created_by=user, approved_by=approver,
            )
    most = max(charge.refundable_amount for charge in charges)
    raise BusinessError(f"Only {most} can go back through a single Paystack payment. "
                        "Refund fewer items, or choose another way to refund.", code="paystack_refund_limit")


@transaction.atomic
def create_refund(user, sale, lines, method, reason, restock=True, approval_pin=None, reference="",
                  through_paystack=False):
    """
    lines: [{"line": sale_line_id, "quantity": n}]
    With through_paystack, the caller must pass refund.paystack_refund to paystack.send_refund afterwards.
    """
    approver = require_permission_or_approval(user, "refund", approval_pin, "Refunds need manager approval.")
    sale = Sale.objects.select_for_update().get(pk=sale.pk)
    if sale.status == Sale.Status.VOIDED:
        raise BusinessError("This sale was voided.")
    if not reason:
        raise BusinessError("Give a reason for the refund.")
    if method == PaymentMethod.CREDIT and not sale.customer:
        raise BusinessError("Only sales to a customer can be refunded to their account.")
    if method == PaymentMethod.POINTS:
        raise BusinessError("Refund points sales in cash or to the customer's account.")
    if through_paystack and method != PaymentMethod.MOMO:
        raise BusinessError("Only Mobile Money can be refunded through Paystack.")
    shift = require_shift(user) if method == PaymentMethod.CASH else None

    refund = Refund.objects.create(
        number=next_document_number(sale.branch, "refund"), sale=sale, shift=shift, user=user,
        approved_by=approver, method=method, reason=reason[:255], restocked=restock, reference=reference,
    )
    total = tax_total = ZERO
    sale_lines = {sl.pk: sl for sl in sale.lines.select_for_update().select_related("variant")}
    for entry in lines:
        sl = sale_lines.get(int(entry["line"]))
        qty = D(entry["quantity"])
        if sl is None or qty <= 0:
            continue
        remaining = sl.quantity - sl.refunded_quantity
        if qty > remaining:
            raise BusinessError(f"Only {remaining.normalize():f} of {sl.name} can still be refunded.")
        if qty == remaining:
            # Last units: refund exactly what is left so rounding never leaves pesewas behind.
            done = sum((rl.amount for rl in sl.refund_lines.all()), ZERO)
            done_tax = sum((rl.tax_amount for rl in sl.refund_lines.all()), ZERO)
            amount, tax = sl.total - done, sl.tax_amount - done_tax
        else:
            amount = money(sl.total * qty / sl.quantity)
            tax = money(sl.tax_amount * qty / sl.quantity)
        RefundLine.objects.create(refund=refund, sale_line=sl, quantity=qty, amount=amount, tax_amount=tax)
        sl.refunded_quantity += qty
        sl.save(update_fields=["refunded_quantity"])
        if restock and sl.track_stock:
            change_stock(sale.branch, sl.variant, qty, "refund", user=user, reference=refund.number,
                         unit_cost=sl.unit_cost)
        total += amount
        tax_total += tax
    if total <= 0:
        raise BusinessError("Choose at least one item to refund.")
    refund.amount, refund.tax_amount = total, tax_total
    refund.save(update_fields=["amount", "tax_amount"])
    if through_paystack:
        _create_paystack_refund(user, sale, refund, approver)

    all_back = all(sl.refunded_quantity >= sl.quantity for sl in sale_lines.values())
    sale.status = Sale.Status.REFUNDED if all_back else Sale.Status.PARTIALLY_REFUNDED
    sale.save(update_fields=["status"])
    fraction = total / sale.total if sale.total else ZERO
    _reverse_customer_effects(sale, fraction, user, method, total)
    audit("refund", user, "sale", sale.pk, approved_by=approver, refund=refund.number, amount=str(total),
          method=method, reason=reason)
    return refund


@transaction.atomic
def void_sale(user, sale, reason, approval_pin=None):
    """Cancel a sale made by mistake. Only within the same open shift and before any refund."""
    approver = require_permission_or_approval(user, "void", approval_pin, "Voiding a sale needs manager approval.")
    sale = Sale.objects.select_for_update().get(pk=sale.pk)
    if sale.status != Sale.Status.COMPLETED:
        raise BusinessError("Only completed sales without refunds can be voided. Use a refund instead.")
    if sale.shift and sale.shift.status != "open":
        raise BusinessError("The shift for this sale is closed. Use a refund instead.")
    if not reason:
        raise BusinessError("Give a reason for voiding.")
    if sale.payments.filter(paystack_charge__isnull=False).exists():
        raise BusinessError("This sale was paid through Paystack. Use a refund so the money goes back to the customer.",
                            code="paystack_void")
    for sl in sale.lines.select_related("variant"):
        if sl.track_stock:
            change_stock(sale.branch, sl.variant, sl.quantity, "void", user=user, reference=sale.invoice_number,
                         unit_cost=sl.unit_cost)
    customer = sale.customer
    if customer:
        customer = Customer.objects.select_for_update().get(pk=customer.pk)
        credit = sum((p.amount for p in sale.payments.filter(method=PaymentMethod.CREDIT)), ZERO)
        if credit:
            customer.balance -= credit
            CustomerTransaction.objects.create(
                customer=customer, kind=CustomerTransaction.Kind.CREDIT_REFUND, amount=-credit, sale=sale,
                user=user, note="Sale voided",
            )
        if sale.points_redeemed:
            customer.loyalty_points += sale.points_redeemed
        if sale.points_earned:
            customer.loyalty_points = max(customer.loyalty_points - sale.points_earned, ZERO)
        if sale.points_redeemed or sale.points_earned:
            CustomerTransaction.objects.create(
                customer=customer, kind=CustomerTransaction.Kind.POINTS_REVERSED,
                points=sale.points_redeemed - sale.points_earned, sale=sale, user=user, note="Sale voided",
            )
        customer.save(update_fields=["balance", "loyalty_points"])
    sale.status = Sale.Status.VOIDED
    sale.voided_at = timezone.now()
    sale.voided_by = user
    sale.void_reason = reason[:255]
    sale.save(update_fields=["status", "voided_at", "voided_by", "void_reason"])
    audit("sale_voided", user, "sale", sale.pk, approved_by=approver, invoice=sale.invoice_number,
          total=str(sale.total), reason=reason)
    return sale
