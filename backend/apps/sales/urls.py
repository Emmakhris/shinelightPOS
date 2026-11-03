from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("held", views.HeldSaleViewSet, basename="held-sale")
router.register("refunds", views.RefundViewSet, basename="refund")
router.register("", views.SaleViewSet, basename="sale")

urlpatterns = [
    path("quote/", views.quote),
    path("checkout/", views.checkout),
    path("", include(router.urls)),
]
