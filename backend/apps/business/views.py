from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Role, User
from apps.accounts.permissions import HasPerm
from apps.accounts.services import audit

from .models import GHANA_DEFAULT_TAXES, Branch, BusinessProfile, Expense, TaxRate
from .serializers import (
    BranchSerializer, BusinessProfileSerializer, ExpenseSerializer, SetupSerializer, TaxRateSerializer,
)


def _setup_done():
    return BusinessProfile.get().setup_complete or User.objects.exists()


@api_view(["GET"])
@permission_classes([AllowAny])
def setup_status(request):
    profile = BusinessProfile.get()
    return Response({"setup_complete": _setup_done(), "business_name": profile.name})


@api_view(["POST"])
@permission_classes([AllowAny])
def setup(request):
    """First-run wizard. Only works while the system has no users."""
    if _setup_done():
        return Response({"detail": "Setup has already been completed."}, status=status.HTTP_400_BAD_REQUEST)
    s = SetupSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    d = s.validated_data
    with transaction.atomic():
        profile = BusinessProfile.get()
        profile.name = d["business_name"]
        profile.phone = d.get("phone", "")
        profile.email = d.get("email", "")
        profile.address = d.get("address", "")
        profile.tin = d.get("tin", "")
        profile.vat_registered = d["vat_registered"]
        profile.retail_mode = d["retail_mode"]
        profile.restaurant_mode = d["restaurant_mode"]
        profile.prices_include_tax = d["prices_include_tax"]
        profile.setup_complete = True
        profile.save()
        Branch.default()
        if not TaxRate.objects.exists():
            for t in GHANA_DEFAULT_TAXES:
                # Shops that are not VAT registered charge no VAT/levies; rows are kept for later.
                TaxRate.objects.create(**t, is_active=d["vat_registered"])
        owner = User(
            username=d["owner_username"], first_name=d["owner_first_name"],
            last_name=d.get("owner_last_name", ""), role=Role.OWNER, is_staff=True, is_superuser=True,
        )
        owner.set_password(d["owner_password"])
        owner.set_pin(d["owner_pin"])
        owner.save()
        audit("setup_completed", owner)
        if d["demo_data"]:
            from .demo import load_demo_data

            load_demo_data()
    return Response({"setup_complete": True}, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, MultiPartParser, FormParser])
def business_settings(request):
    profile = BusinessProfile.get()
    if request.method == "GET":
        return Response(BusinessProfileSerializer(profile, context={"request": request}).data)
    if not request.user.has_pos_perm("manage_settings"):
        return Response({"detail": "Only the owner can change settings."}, status=status.HTTP_403_FORBIDDEN)
    s = BusinessProfileSerializer(profile, data=request.data, partial=True, context={"request": request})
    s.is_valid(raise_exception=True)
    s.save()
    audit("settings_updated", request.user, "business", profile.pk, fields=sorted(request.data.keys()))
    return Response(s.data)


@api_view(["GET", "POST"])
@permission_classes([HasPerm("manage_settings")])
def backups(request):
    """List backups, or take one now. Restoring is done from the shop PC (scripts/restore.ps1)."""
    from .backups import BackupError, create_backup, list_backups

    if request.method == "POST":
        try:
            folder = create_backup(label="manual")
        except BackupError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        audit("backup_created", request.user, "backup", folder.name)
        return Response({"name": folder.name}, status=status.HTTP_201_CREATED)
    return Response(list_backups())


class BranchViewSet(viewsets.ModelViewSet):
    queryset = Branch.objects.all()
    serializer_class = BranchSerializer
    permission_classes = [HasPerm("manage_settings", read_perm="sell")]


class TaxRateViewSet(viewsets.ModelViewSet):
    queryset = TaxRate.objects.all()
    serializer_class = TaxRateSerializer
    permission_classes = [HasPerm("manage_settings", read_perm="sell")]

    def perform_update(self, serializer):
        tax = serializer.save()
        audit("tax_rate_updated", self.request.user, "tax_rate", tax.pk, rate=str(tax.rate), active=tax.is_active)


class ExpenseViewSet(viewsets.ModelViewSet):
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer
    permission_classes = [HasPerm("view_reports")]
    filterset_fields = {"date": ["gte", "lte"], "category": ["exact"]}
