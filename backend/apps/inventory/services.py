from django.db import transaction

from apps.business.models import BusinessProfile
from apps.common.exceptions import BusinessError
from apps.common.money import D

from .models import StockLevel, StockMovement


def change_stock(branch, variant, change, reason, user=None, reference="", note="", unit_cost=None,
                 enforce_available=False):
    """
    The only way stock changes. Locks the stock row so two tills selling the last item
    cannot both succeed, then writes the ledger entry.
    """
    change = D(change)
    with transaction.atomic():
        level, _ = StockLevel.objects.get_or_create(branch=branch, variant=variant)
        level = StockLevel.objects.select_for_update().get(pk=level.pk)
        new_qty = level.quantity + change
        if enforce_available and change < 0 and new_qty < 0 and not BusinessProfile.get().allow_negative_stock:
            raise BusinessError(
                f"Not enough stock for {variant.full_name}: {level.quantity.normalize():f} left.",
                code="insufficient_stock",
            )
        level.quantity = new_qty
        level.save(update_fields=["quantity"])
        return StockMovement.objects.create(
            branch=branch, variant=variant, change=change, quantity_after=new_qty, reason=reason,
            reference=reference, note=note[:255], user=user,
            unit_cost=variant.cost_price if unit_cost is None else unit_cost,
        )


def set_counted_stock(branch, variant, counted, user=None, note=""):
    """Stock count: record the difference between what the system expected and what was counted."""
    with transaction.atomic():
        level, _ = StockLevel.objects.get_or_create(branch=branch, variant=variant)
        level = StockLevel.objects.select_for_update().get(pk=level.pk)
        diff = D(counted) - level.quantity
        if diff == 0:
            return None
        return change_stock(branch, variant, diff, "count", user=user, note=note or "Stock count")
