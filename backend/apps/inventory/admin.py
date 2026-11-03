from django.contrib import admin

from .models import PurchaseOrder, PurchaseOrderLine, StockLevel, StockMovement, Supplier


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 0


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ["number", "supplier", "status", "created_at"]
    inlines = [PurchaseOrderLineInline]


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ["created_at", "variant", "change", "quantity_after", "reason", "reference", "user"]
    list_filter = ["reason"]
    # The ledger must not be edited by hand; corrections go through an adjustment.
    readonly_fields = [f.name for f in StockMovement._meta.fields]


admin.site.register(StockLevel)
admin.site.register(Supplier)
