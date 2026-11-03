from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import HasPerm
from apps.accounts.services import audit
from apps.common.exceptions import BusinessError
from apps.shifts.services import current_shift

from .models import Customer, CustomerTransaction
from .serializers import BalancePaymentSerializer, CustomerSerializer, CustomerTransactionSerializer


class CustomerViewSet(viewsets.ModelViewSet):
    serializer_class = CustomerSerializer
    permission_classes = [HasPerm("manage_customers", read_perm="sell")]
    search_fields = ["name", "phone", "email"]
    filterset_fields = ["is_active"]
    ordering_fields = ["name", "balance", "loyalty_points", "created_at"]

    def get_queryset(self):
        qs = Customer.objects.all()
        if self.request.query_params.get("owing"):
            qs = qs.filter(balance__gt=0)
        return qs

    def destroy(self, request, *args, **kwargs):
        customer = self.get_object()
        if customer.balance:
            raise BusinessError("This customer still has a balance. Settle it before removing them.")
        customer.is_active = False
        customer.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def transactions(self, request, pk=None):
        customer = self.get_object()
        qs = customer.transactions.select_related("sale", "user")[:200]
        return Response(CustomerTransactionSerializer(qs, many=True).data)

    @action(detail=True, methods=["get"])
    def sales(self, request, pk=None):
        from apps.sales.serializers import SaleListSerializer

        customer = self.get_object()
        qs = customer.sales.select_related("cashier").order_by("-created_at")[:100]
        return Response(SaleListSerializer(qs, many=True).data)

    @action(detail=True, methods=["post"])
    def pay_balance(self, request, pk=None):
        """The customer pays off some of what they owe. Cash goes into the current shift's drawer."""
        s = BalancePaymentSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        shift = current_shift(request.user)
        if d["method"] == "cash" and shift is None:
            raise BusinessError("Open a shift before taking cash.", code="no_open_shift")
        with transaction.atomic():
            customer = Customer.objects.select_for_update().get(pk=pk)
            if d["amount"] > customer.balance:
                raise BusinessError(f"{customer.name} only owes {customer.balance}.")
            customer.balance -= d["amount"]
            customer.save(update_fields=["balance"])
            CustomerTransaction.objects.create(
                customer=customer, kind=CustomerTransaction.Kind.CREDIT_PAYMENT, amount=-d["amount"],
                method=d["method"], reference=d.get("reference", ""), note=d.get("note", ""),
                shift=shift, user=request.user,
            )
        audit("customer_balance_paid", request.user, "customer", customer.pk, amount=str(d["amount"]),
              method=d["method"])
        return Response(CustomerSerializer(customer).data)
