from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("areas", views.FloorAreaViewSet)
router.register("tables", views.TableViewSet)
router.register("orders", views.OrderViewSet, basename="order")
router.register("tickets", views.KitchenTicketViewSet, basename="ticket")

urlpatterns = [
    path("floor/", views.floor),
    path("", include(router.urls)),
]
