from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("branches", views.BranchViewSet)
router.register("tax-rates", views.TaxRateViewSet)
router.register("expenses", views.ExpenseViewSet)

urlpatterns = [
    path("setup/status/", views.setup_status),
    path("setup/", views.setup),
    path("settings/", views.business_settings),
    path("backups/", views.backups),
    path("", include(router.urls)),
]
