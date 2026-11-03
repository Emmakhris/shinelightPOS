from django.contrib import admin

from .models import CashMovement, Shift


class CashMovementInline(admin.TabularInline):
    model = CashMovement
    extra = 0


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ["user", "register_name", "status", "opened_at", "closed_at", "expected_cash", "counted_cash"]
    list_filter = ["status"]
    inlines = [CashMovementInline]
