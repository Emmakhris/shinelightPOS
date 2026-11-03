import csv
import io

from django.db import transaction
from django.db.models import Count, Q
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from apps.accounts.permissions import HasPerm
from apps.accounts.services import audit
from apps.business.models import Branch, TaxCategory
from apps.common.csvexport import csv_response
from apps.common.money import D
from apps.inventory.models import StockLevel
from apps.inventory.services import change_stock

from .models import Barcode, Category, ModifierGroup, Product, Unit, Variant
from .serializers import CategorySerializer, ModifierGroupSerializer, ProductSerializer

CatalogPerm = HasPerm("manage_catalog", read_perm="sell")


def stock_map(branch=None, variant_ids=None):
    qs = StockLevel.objects.filter(branch=branch or Branch.default())
    if variant_ids is not None:
        qs = qs.filter(variant_id__in=variant_ids)
    return dict(qs.values_list("variant_id", "quantity"))


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [CatalogPerm]
    search_fields = ["name"]

    def get_queryset(self):
        return Category.objects.annotate(product_count=Count("products", filter=Q(products__is_active=True)))


class ModifierGroupViewSet(viewsets.ModelViewSet):
    serializer_class = ModifierGroupSerializer
    permission_classes = [CatalogPerm]
    queryset = ModifierGroup.objects.prefetch_related("modifiers")


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [CatalogPerm]
    filterset_fields = ["category", "is_active", "track_stock", "tax_category"]
    search_fields = ["name", "variants__sku", "variants__barcodes__code"]
    ordering_fields = ["name", "created_at", "updated_at"]

    def get_queryset(self):
        return (
            Product.objects.select_related("category")
            .prefetch_related("variants__barcodes", "modifier_groups")
            .distinct()
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["stock_map"] = stock_map()
        return ctx

    def perform_create(self, serializer):
        product = serializer.save()
        audit("product_created", self.request.user, "product", product.pk, name=product.name)

    def perform_update(self, serializer):
        before = {v.pk: str(v.price) for v in serializer.instance.variants.all()}
        product = serializer.save()
        after = {v.pk: str(v.price) for v in product.variants.all()}
        changed = {k: [before.get(k), v] for k, v in after.items() if before.get(k) != v}
        audit("product_updated", self.request.user, "product", product.pk, name=product.name, price_changes=changed)

    def destroy(self, request, *args, **kwargs):
        # Products appear on old receipts; archive instead of deleting.
        product = self.get_object()
        product.is_active = False
        product.save(update_fields=["is_active"])
        audit("product_archived", request.user, "product", product.pk, name=product.name)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post", "delete"], parser_classes=[MultiPartParser])
    def image(self, request, pk=None):
        product = self.get_object()
        if request.method == "DELETE":
            product.image.delete(save=True)
        else:
            upload = request.FILES.get("image")
            if not upload:
                return Response({"detail": "Choose an image file."}, status=status.HTTP_400_BAD_REQUEST)
            product.image.save(upload.name, upload, save=True)
        return Response(self.get_serializer(product).data)

    @action(detail=False, methods=["get"])
    def export(self, request):
        stock = stock_map()
        rows = []
        for p in self.get_queryset().filter(is_active=True):
            for v in p.variants.all():
                if not v.is_active:
                    continue
                rows.append({
                    "name": p.name, "variant": v.name, "sku": v.sku or "",
                    "barcodes": "|".join(b.code for b in v.barcodes.all()),
                    "category": p.category.name if p.category else "", "unit": p.unit,
                    "price": v.price, "cost_price": v.cost_price, "tax_category": p.tax_category,
                    "track_stock": "yes" if p.track_stock else "no", "stock": stock.get(v.pk, 0),
                    "low_stock_threshold": p.low_stock_threshold,
                })
        columns = [(k, k) for k in ["name", "variant", "sku", "barcodes", "category", "unit", "price",
                                    "cost_price", "tax_category", "track_stock", "stock", "low_stock_threshold"]]
        return csv_response("products.csv", columns, rows)

    @action(detail=False, methods=["post"], url_path="import", parser_classes=[MultiPartParser])
    def import_csv(self, request):
        """
        Import simple products. Columns: name, sku, barcodes (| separated), category, unit, price,
        cost_price, tax_category, track_stock, stock, low_stock_threshold. Rows whose SKU already
        exists update that product's price/cost; stock is only set for new products.
        """
        upload = request.FILES.get("file")
        if not upload:
            return Response({"detail": "Choose a CSV file."}, status=status.HTTP_400_BAD_REQUEST)
        reader = csv.DictReader(io.StringIO(upload.read().decode("utf-8-sig")))
        created = updated = 0
        errors = []
        branch = Branch.default()
        units = set(Unit.values)
        for line_no, row in enumerate(reader, start=2):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            name = row.get("name")
            if not name:
                continue
            try:
                with transaction.atomic():
                    sku = row.get("sku") or None
                    variant = Variant.objects.filter(sku=sku).select_related("product").first() if sku else None
                    price = D(row.get("price") or 0)
                    cost = D(row.get("cost_price") or 0)
                    if variant:
                        variant.price, variant.cost_price = price, cost
                        variant.save(update_fields=["price", "cost_price"])
                        updated += 1
                        continue
                    category = None
                    if row.get("category"):
                        category, _ = Category.objects.get_or_create(name=row["category"])
                    tax_cat = row.get("tax_category") or TaxCategory.STANDARD
                    if tax_cat not in TaxCategory.values:
                        raise ValueError(f"tax_category must be one of {', '.join(TaxCategory.values)}")
                    unit = row.get("unit") or Unit.PIECE
                    if unit not in units:
                        raise ValueError(f"unknown unit '{unit}'")
                    track = (row.get("track_stock") or "yes").lower() in ("yes", "y", "true", "1")
                    product = Product.objects.create(
                        name=name, category=category, unit=unit, tax_category=tax_cat, track_stock=track,
                        low_stock_threshold=D(row.get("low_stock_threshold") or 5),
                    )
                    variant = Variant.objects.create(product=product, sku=sku, price=price, cost_price=cost)
                    for code in filter(None, (row.get("barcodes") or row.get("barcode") or "").split("|")):
                        if Barcode.objects.filter(code=code.strip()).exists():
                            raise ValueError(f"barcode {code} already exists")
                        Barcode.objects.create(variant=variant, code=code.strip())
                    if track and D(row.get("stock") or 0):
                        change_stock(branch, variant, D(row["stock"]), "opening", user=request.user, note="CSV import")
                    created += 1
            except Exception as exc:  # report every bad row instead of failing the whole file
                errors.append(f"Row {line_no}: {exc}")
        audit("products_imported", request.user, created=created, updated=updated, errors=len(errors))
        return Response({"created": created, "updated": updated, "errors": errors})


def _pos_items(variants):
    stock = stock_map(variant_ids=[v.pk for v in variants])
    items = []
    for v in variants:
        p = v.product
        items.append({
            "id": v.pk,
            "product_id": p.pk,
            "name": v.full_name,
            "product_name": p.name,
            "variant_name": v.name,
            "sku": v.sku,
            "price": str(v.price),
            "barcodes": [b.code for b in v.barcodes.all()],
            "category": p.category_id,
            "category_color": p.category.color if p.category else None,
            "tax_category": p.tax_category,
            "unit": p.unit,
            "allows_fraction": p.allows_fraction,
            "track_stock": p.track_stock,
            "stock": str(stock.get(v.pk, 0)),
            "is_kitchen_item": p.is_kitchen_item,
            "image": p.image.url if p.image else None,
            "modifier_groups": [g.pk for g in p.modifier_groups.all()],
        })
    return items


def _sellable_variants():
    return (
        Variant.objects.filter(is_active=True, product__is_active=True)
        .select_related("product__category")
        .prefetch_related("barcodes", "product__modifier_groups")
    )


@api_view(["GET"])
@permission_classes([HasPerm("sell")])
def pos_items(request):
    """Everything the register needs to show the product grid, in one request."""
    return Response(_pos_items(list(_sellable_variants())))


@api_view(["GET"])
@permission_classes([HasPerm("sell")])
def lookup(request):
    """Find an item by scanned barcode or typed SKU."""
    code = (request.query_params.get("code") or "").strip()
    if not code:
        return Response({"detail": "No code given."}, status=status.HTTP_400_BAD_REQUEST)
    variant = _sellable_variants().filter(Q(barcodes__code=code) | Q(sku__iexact=code)).first()
    if not variant:
        return Response({"detail": f"No item with code {code}."}, status=status.HTTP_404_NOT_FOUND)
    return Response(_pos_items([variant])[0])
