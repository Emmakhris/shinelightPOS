from django.contrib import admin

from .models import Customer, CustomerTransaction


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ["name", "phone", "balance", "loyalty_points", "is_active"]
    search_fields = ["name", "phone"]


admin.site.register(CustomerTransaction)
