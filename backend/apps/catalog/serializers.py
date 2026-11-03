from django.db import transaction
from rest_framework import serializers

from apps.business.models import Branch
from apps.inventory.services import change_stock

from .models import Barcode, Category, Modifier, ModifierGroup, Product, Variant


class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Category
        fields = ["id", "name", "color", "sort_order", "is_active", "product_count"]


class ModifierSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = Modifier
        fields = ["id", "name", "price", "is_active", "sort_order"]


class ModifierGroupSerializer(serializers.ModelSerializer):
    modifiers = ModifierSerializer(many=True)

    class Meta:
        model = ModifierGroup
        fields = ["id", "name", "min_select", "max_select", "sort_order", "modifiers"]

    @transaction.atomic
    def create(self, validated_data):
        modifiers = validated_data.pop("modifiers", [])
        group = ModifierGroup.objects.create(**validated_data)
        for m in modifiers:
            m.pop("id", None)
            Modifier.objects.create(group=group, **m)
        return group

    @transaction.atomic
    def update(self, instance, validated_data):
        modifiers = validated_data.pop("modifiers", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        if modifiers is not None:
            keep = []
            for m in modifiers:
                mid = m.pop("id", None)
                obj = instance.modifiers.filter(pk=mid).first() if mid else None
                if obj:
                    for k, v in m.items():
                        setattr(obj, k, v)
                    obj.save()
                else:
                    obj = Modifier.objects.create(group=instance, **m)
                keep.append(obj.pk)
            instance.modifiers.exclude(pk__in=keep).delete()
        return instance


class VariantSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    barcodes = serializers.ListField(child=serializers.CharField(max_length=64), required=False, write_only=True)
    stock = serializers.SerializerMethodField()
    opening_stock = serializers.DecimalField(max_digits=14, decimal_places=3, write_only=True, required=False)
    sku = serializers.CharField(max_length=60, required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = Variant
        fields = ["id", "name", "sku", "price", "cost_price", "is_active", "sort_order",
                  "barcodes", "stock", "opening_stock"]

    def get_stock(self, instance):
        stock_map = self.context.get("stock_map")
        return None if stock_map is None else str(stock_map.get(instance.pk, 0))

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["barcodes"] = [b.code for b in instance.barcodes.all()]
        return data


class ProductSerializer(serializers.ModelSerializer):
    variants = VariantSerializer(many=True)
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    image = serializers.ImageField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "name", "category", "category_name", "description", "unit", "tax_category",
            "track_stock", "low_stock_threshold", "has_variants", "is_kitchen_item",
            "modifier_groups", "image", "is_active", "variants", "created_at", "updated_at",
        ]

    def validate(self, attrs):
        variants = attrs.get("variants")
        if variants is not None:
            if not variants:
                raise serializers.ValidationError({"variants": "A product needs at least one price."})
            has_variants = attrs.get("has_variants", getattr(self.instance, "has_variants", False))
            if not has_variants and len(variants) > 1:
                raise serializers.ValidationError({"variants": "Turn on variants to add more than one."})
            own_ids = {v.get("id") for v in variants if v.get("id")}
            seen = set()
            for v in variants:
                for code in v.get("barcodes", []):
                    if code in seen:
                        raise serializers.ValidationError({"variants": f"Barcode {code} is listed twice."})
                    seen.add(code)
                    clash = Barcode.objects.filter(code=code).exclude(variant_id__in=own_ids).first()
                    if clash:
                        raise serializers.ValidationError(
                            {"variants": f"Barcode {code} already belongs to {clash.variant.full_name}."}
                        )
                sku = v.get("sku") or None
                v["sku"] = sku
                if sku and Variant.objects.filter(sku=sku).exclude(pk__in=own_ids).exists():
                    raise serializers.ValidationError({"variants": f"SKU {sku} is already used."})
        return attrs

    def _save_variants(self, product, variants):
        request = self.context.get("request")
        user = request.user if request else None
        branch = Branch.default()
        keep = []
        for i, v in enumerate(variants):
            vid = v.pop("id", None)
            barcodes = v.pop("barcodes", None)
            opening = v.pop("opening_stock", None)
            v.setdefault("sort_order", i)
            if not product.has_variants:
                v["name"] = ""
            obj = product.variants.filter(pk=vid).first() if vid else None
            if obj:
                for k, val in v.items():
                    setattr(obj, k, val)
                obj.save()
            else:
                obj = Variant.objects.create(product=product, **v)
            if barcodes is not None:
                obj.barcodes.exclude(code__in=barcodes).delete()
                for code in barcodes:
                    Barcode.objects.get_or_create(variant=obj, code=code.strip())
            if opening and product.track_stock:
                change_stock(branch, obj, opening, "opening", user=user, note="Opening stock")
            keep.append(obj.pk)
        # Variants already used in sales cannot be deleted; hide them instead.
        product.variants.exclude(pk__in=keep).update(is_active=False)

    @transaction.atomic
    def create(self, validated_data):
        variants = validated_data.pop("variants")
        groups = validated_data.pop("modifier_groups", [])
        product = Product.objects.create(**validated_data)
        product.modifier_groups.set(groups)
        self._save_variants(product, variants)
        return product

    @transaction.atomic
    def update(self, instance, validated_data):
        variants = validated_data.pop("variants", None)
        groups = validated_data.pop("modifier_groups", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        if groups is not None:
            instance.modifier_groups.set(groups)
        if variants is not None:
            self._save_variants(instance, variants)
        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self.context.get("include_inactive_variants"):
            data["variants"] = [v for v in data["variants"] if v["is_active"]]
        return data
