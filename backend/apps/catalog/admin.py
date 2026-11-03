from django.contrib import admin

from .models import Barcode, Category, Modifier, ModifierGroup, Product, Variant


class VariantInline(admin.TabularInline):
    model = Variant
    extra = 0


class ModifierInline(admin.TabularInline):
    model = Modifier
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "tax_category", "track_stock", "is_active"]
    list_filter = ["category", "is_active", "tax_category"]
    search_fields = ["name", "variants__sku"]
    inlines = [VariantInline]


@admin.register(ModifierGroup)
class ModifierGroupAdmin(admin.ModelAdmin):
    inlines = [ModifierInline]


admin.site.register(Category)
admin.site.register(Barcode)
