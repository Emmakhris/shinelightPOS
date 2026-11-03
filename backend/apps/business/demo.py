"""Sample products, tables and a customer so a new install can be tried straight away."""
from django.db import transaction

from apps.catalog.models import Barcode, Category, Modifier, ModifierGroup, Product, Variant
from apps.customers.models import Customer
from apps.inventory.models import Supplier
from apps.inventory.services import change_stock
from apps.restaurant.models import FloorArea, Table

from .models import Branch

# name, category, price, cost, barcode, stock, extra fields
RETAIL = [
    ("Coca-Cola 500ml", "Drinks", "8.00", "5.50", "5449000000996", 48, {}),
    ("Voltic Water 750ml", "Drinks", "4.00", "2.50", "6034000123456", 60, {}),
    ("Malta Guinness 330ml", "Drinks", "10.00", "7.00", "5000213004441", 24, {}),
    ("Milo 400g Tin", "Groceries", "65.00", "52.00", "7613035239906", 12, {}),
    ("Ideal Milk 160g", "Groceries", "9.50", "7.20", "8712566479733", 36, {}),
    ("Frytol Oil 1L", "Groceries", "45.00", "38.00", "6034000654321", 15, {}),
    ("Rice (loose) per kg", "Groceries", "18.00", "13.00", "", 50, {"unit": "kg", "tax_category": "exempt"}),
    ("Key Soap", "Toiletries", "7.00", "5.00", "6034000111222", 40, {}),
    ("Pepsodent Toothpaste", "Toiletries", "15.00", "11.00", "8714100737802", 4, {"low_stock_threshold": 5}),
]

FOOD = [
    ("Jollof Rice", "12.00", ["Protein", "Extras"]),
    ("Waakye", "10.00", ["Protein", "Extras"]),
    ("Banku & Tilapia", "45.00", ["Extras"]),
    ("Fried Rice", "15.00", ["Protein", "Extras"]),
    ("Kelewele", "10.00", []),
]


@transaction.atomic
def load_demo_data():
    branch = Branch.default()
    colors = {"Drinks": "#0ea5e9", "Groceries": "#16a34a", "Toiletries": "#a855f7", "Food": "#f97316"}
    cats = {name: Category.objects.get_or_create(name=name, defaults={"color": c, "sort_order": i})[0]
            for i, (name, c) in enumerate(colors.items())}

    for i, (name, cat, price, cost, barcode, stock, extra) in enumerate(RETAIL, start=1):
        product = Product.objects.create(name=name, category=cats[cat], **extra)
        variant = Variant.objects.create(product=product, sku=f"SKU{i:04d}", price=price, cost_price=cost)
        if barcode:
            Barcode.objects.create(variant=variant, code=barcode)
        change_stock(branch, variant, stock, "opening", note="Demo data")

    shirt = Product.objects.create(name="Kente Print T-Shirt", category=cats["Groceries"], has_variants=True)
    for j, size in enumerate(["S", "M", "L"]):
        v = Variant.objects.create(product=shirt, name=size, sku=f"TSHIRT-{size}", price="80.00",
                                   cost_price="45.00", sort_order=j)
        change_stock(branch, v, 10, "opening", note="Demo data")
    shirt.category = Category.objects.get_or_create(name="Clothing", defaults={"color": "#e11d48"})[0]
    shirt.save()

    protein = ModifierGroup.objects.create(name="Protein", min_select=0, max_select=1)
    for name, price in [("Chicken", "15.00"), ("Fish", "20.00"), ("Egg", "5.00"), ("Beef", "18.00")]:
        Modifier.objects.create(group=protein, name=name, price=price)
    extras = ModifierGroup.objects.create(name="Extras", min_select=0, max_select=0, sort_order=1)
    for name, price in [("Shito", "2.00"), ("Fried plantain", "5.00"), ("Salad", "3.00")]:
        Modifier.objects.create(group=extras, name=name, price=price)
    groups = {"Protein": protein, "Extras": extras}
    for i, (name, price, group_names) in enumerate(FOOD, start=1):
        product = Product.objects.create(name=name, category=cats["Food"], unit="plate", track_stock=False,
                                         is_kitchen_item=True)
        Variant.objects.create(product=product, sku=f"FOOD{i:03d}", price=price, cost_price="0")
        product.modifier_groups.set([groups[g] for g in group_names])

    hall = FloorArea.objects.create(name="Main Hall", sort_order=0)
    terrace = FloorArea.objects.create(name="Terrace", sort_order=1)
    for n in range(1, 7):
        Table.objects.create(area=hall, name=f"T{n}", seats=4, sort_order=n)
    for n in range(7, 10):
        Table.objects.create(area=terrace, name=f"T{n}", seats=6, sort_order=n)

    Customer.objects.create(name="Ama Mensah", phone="0244000001", credit_limit="500.00")
    Supplier.objects.create(name="Accra Wholesale Ltd", phone="0302000000", contact_name="Kofi")
