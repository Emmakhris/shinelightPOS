from django.contrib import admin

from .models import Branch, BusinessProfile, Expense, TaxRate

admin.site.register(BusinessProfile)
admin.site.register(Branch)
admin.site.register(Expense)


@admin.register(TaxRate)
class TaxRateAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "rate", "compound", "sort_order", "is_active"]
