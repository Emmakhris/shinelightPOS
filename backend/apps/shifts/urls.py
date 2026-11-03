from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("", views.ShiftViewSet, basename="shift")

urlpatterns = [
    path("current/", views.current),
    path("open/", views.open_),
    path("", include(router.urls)),
]
