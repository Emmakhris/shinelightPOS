from django.urls import path

from . import views

urlpatterns = [
    path("dashboard/", views.dashboard),
    path("summary/", views.summary),
    path("products/", views.products),
    path("categories/", views.categories),
    path("cashiers/", views.cashiers),
    path("payments/", views.payments),
    path("tax/", views.tax),
    path("inventory-valuation/", views.inventory_valuation),
    path("z/", views.z_report),
]
