from django.contrib import admin

from .models import PaystackCharge


@admin.register(PaystackCharge)
class PaystackChargeAdmin(admin.ModelAdmin):
    list_display = ["reference", "created_at", "amount", "phone", "network", "status", "payment"]
    list_filter = ["status", "network"]
    search_fields = ["reference", "phone"]
    readonly_fields = [f.name for f in PaystackCharge._meta.fields]
