from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("categories", views.CategoryViewSet, basename="category")
router.register("modifier-groups", views.ModifierGroupViewSet, basename="modifier-group")
router.register("products", views.ProductViewSet, basename="product")

urlpatterns = [
    path("pos-items/", views.pos_items),
    path("lookup/", views.lookup),
    path("", include(router.urls)),
]
