from django.db import models

from apps.common.fields import MoneyField


class BusinessProfile(models.Model):
    """Single row holding the shop's settings."""

    name = models.CharField(max_length=150, default="My Shop")
    legal_name = models.CharField(max_length=150, blank=True)
    tin = models.CharField("TIN / Ghana Card", max_length=50, blank=True)
    vat_registered = models.BooleanField(default=False)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    logo = models.ImageField(upload_to="logo/", blank=True)

    currency_code = models.CharField(max_length=3, default="GHS")
    currency_symbol = models.CharField(max_length=8, default="GH₵")

    retail_mode = models.BooleanField(default=True)
    restaurant_mode = models.BooleanField(default=False)

    prices_include_tax = models.BooleanField(
        default=True, help_text="Shelf prices already include VAT and levies (common in Ghana retail)."
    )
    allow_negative_stock = models.BooleanField(default=False)
    require_open_shift = models.BooleanField(default=True)
    discount_approval_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=10,
        help_text="Discounts above this percentage of the sale need a manager PIN.",
    )

    loyalty_enabled = models.BooleanField(default=True)
    loyalty_points_per_cedi = models.DecimalField(max_digits=8, decimal_places=4, default=1)
    loyalty_point_value = models.DecimalField(
        max_digits=8, decimal_places=4, default="0.05", help_text="Cedi value of one point at redemption."
    )

    receipt_header = models.TextField(blank=True)
    receipt_footer = models.TextField(blank=True, default="Thank you for your patronage!")
    receipt_width = models.PositiveSmallIntegerField(default=80, choices=[(80, "80 mm"), (58, "58 mm")])
    show_tax_on_receipt = models.BooleanField(default=True)
    evat_enabled = models.BooleanField(default=False, help_text="Report sales, refunds and voids to GRA E-VAT.")

    setup_complete = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    @classmethod
    def get(cls):
        obj = cls.objects.first()
        return obj or cls.objects.create()


class Branch(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=10, unique=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    invoice_prefix = models.CharField(max_length=10, default="INV")
    next_invoice_number = models.PositiveIntegerField(default=1)
    next_refund_number = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "branches"

    def __str__(self):
        return self.name

    @classmethod
    def default(cls):
        branch = cls.objects.filter(is_active=True).order_by("pk").first()
        return branch or cls.objects.create(name="Main", code="MAIN")


class TaxCategory(models.TextChoices):
    STANDARD = "standard", "Standard rated"
    ZERO = "zero", "Zero rated"
    EXEMPT = "exempt", "Exempt"


class TaxRate(models.Model):
    """
    One tax or levy applied to standard-rated items, e.g. VAT, NHIL, GETFund.
    A compound tax is charged on the item value plus all taxes before it in `sort_order`.
    """

    name = models.CharField(max_length=50)
    code = models.CharField(max_length=20, unique=True)
    rate = models.DecimalField(max_digits=6, decimal_places=3)
    compound = models.BooleanField(default=False)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "pk"]

    def __str__(self):
        return f"{self.name} {self.rate}%"


GHANA_DEFAULT_TAXES = [
    # Rates as seeded; confirm the current rates and whether any levy compounds with GRA or your accountant.
    {"name": "NHIL", "code": "NHIL", "rate": "2.5", "compound": False, "sort_order": 1},
    {"name": "GETFund Levy", "code": "GETFUND", "rate": "2.5", "compound": False, "sort_order": 2},
    {"name": "VAT", "code": "VAT", "rate": "15", "compound": False, "sort_order": 3},
]


class Expense(models.Model):
    """Placeholder kept small in Phase 1: lets the owner log shop expenses for the profit report."""

    date = models.DateField()
    category = models.CharField(max_length=60)
    description = models.CharField(max_length=200, blank=True)
    amount = MoneyField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-pk"]
