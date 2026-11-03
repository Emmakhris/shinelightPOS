from django.contrib import admin

from .models import FloorArea, KitchenTicket, Order, OrderItem, Table


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["number", "table", "order_type", "status", "waiter", "created_at"]
    list_filter = ["status", "order_type"]
    inlines = [OrderItemInline]


admin.site.register(FloorArea)
admin.site.register(Table)
admin.site.register(KitchenTicket)
