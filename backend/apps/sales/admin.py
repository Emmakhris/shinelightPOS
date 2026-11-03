from django.contrib import admin

from .models import Payment, Refund, Sale, SaleLine, SaleTax


class ReadOnlyInline(admin.TabularInline):
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class SaleLineInline(ReadOnlyInline):
    model = SaleLine


class PaymentInline(ReadOnlyInline):
    model = Payment


class SaleTaxInline(ReadOnlyInline):
    model = SaleTax


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    """Sales are financial records: viewable in admin, never editable."""

    list_display = ["invoice_number", "created_at", "status", "cashier", "customer", "total"]
    list_filter = ["status", "order_type"]
    search_fields = ["invoice_number"]
    inlines = [SaleLineInline, SaleTaxInline, PaymentInline]

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ["number", "sale", "amount", "method", "created_at", "user"]

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
