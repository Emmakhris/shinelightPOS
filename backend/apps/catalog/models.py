from django.db import models

from apps.business.models import TaxCategory
from apps.common.fields import MoneyField, QtyField


class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)
    color = models.CharField(max_length=20, default="#2563eb")
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class ModifierGroup(models.Model):
    """E.g. 'Size' (pick 1) or 'Extras' (pick any). Attached to products, mainly in restaurant mode."""

    name = models.CharField(max_length=80)
    min_select = models.PositiveSmallIntegerField(default=0)
    max_select = models.PositiveSmallIntegerField(default=0, help_text="0 means no limit.")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class Modifier(models.Model):
    group = models.ForeignKey(ModifierGroup, on_delete=models.CASCADE, related_name="modifiers")
    name = models.CharField(max_length=80)
    price = MoneyField(help_text="Added to the item price. Can be 0.")
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return f"{self.group.name}: {self.name}"


class Unit(models.TextChoices):
    PIECE = "pc", "Piece"
    KG = "kg", "Kilogram"
    GRAM = "g", "Gram"
    LITRE = "l", "Litre"
    ML = "ml", "Millilitre"
    METRE = "m", "Metre"
    PACK = "pack", "Pack"
    BOX = "box", "Box"
    PLATE = "plate", "Plate"


FRACTIONAL_UNITS = {Unit.KG, Unit.GRAM, Unit.LITRE, Unit.ML, Unit.METRE}


class Product(models.Model):
    name = models.CharField(max_length=150, db_index=True)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="products")
    description = models.TextField(blank=True)
    unit = models.CharField(max_length=10, choices=Unit.choices, default=Unit.PIECE)
    tax_category = models.CharField(max_length=10, choices=TaxCategory.choices, default=TaxCategory.STANDARD)
    track_stock = models.BooleanField(default=True)
    low_stock_threshold = QtyField(default=5)
    has_variants = models.BooleanField(default=False)
    is_kitchen_item = models.BooleanField(default=False, help_text="Print on kitchen tickets.")
    modifier_groups = models.ManyToManyField(ModifierGroup, blank=True, related_name="products")
    image = models.ImageField(upload_to="products/", blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def allows_fraction(self):
        return self.unit in FRACTIONAL_UNITS


class Variant(models.Model):
    """
    What is actually sold and stocked. A product without variants has exactly one
    variant with an empty name, so sales and stock always point at a Variant.
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    name = models.CharField(max_length=100, blank=True)
    sku = models.CharField(max_length=60, unique=True, null=True, blank=True)
    price = MoneyField()
    cost_price = MoneyField()
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["product__name", "sort_order", "pk"]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f"{self.product.name} - {self.name}" if self.name else self.product.name


class Barcode(models.Model):
    variant = models.ForeignKey(Variant, on_delete=models.CASCADE, related_name="barcodes")
    code = models.CharField(max_length=64, unique=True)

    def __str__(self):
        return self.code
