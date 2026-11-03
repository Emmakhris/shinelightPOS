from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("movements", views.StockMovementViewSet, basename="movement")
router.register("suppliers", views.SupplierViewSet)
router.register("purchase-orders", views.PurchaseOrderViewSet, basename="purchase-order")

urlpatterns = [
    path("stock/", views.stock_levels),
    path("adjust/", views.adjust),
    path("count/", views.count),
    path("", include(router.urls)),
]
