from django.contrib import admin

from .models import PaystackCharge, PaystackRefund


@admin.register(PaystackCharge)
class PaystackChargeAdmin(admin.ModelAdmin):
    list_display = ["reference", "created_at", "amount", "phone", "network", "status", "payment"]
    list_filter = ["status", "network"]
    search_fields = ["reference", "phone"]
    readonly_fields = [f.name for f in PaystackCharge._meta.fields]


@admin.register(PaystackRefund)
class PaystackRefundAdmin(admin.ModelAdmin):
    list_display = ["reference", "created_at", "amount", "status", "charge", "sale_refund"]
    list_filter = ["status"]
    search_fields = ["reference", "charge__reference", "charge__phone"]
    readonly_fields = [f.name for f in PaystackRefund._meta.fields]
