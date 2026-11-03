from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

router = DefaultRouter()
router.register("users", views.UserViewSet, basename="user")
router.register("audit-log", views.AuditLogViewSet, basename="audit-log")

urlpatterns = [
    path("auth/login/", views.login),
    path("auth/pin-login/", views.pin_login),
    path("auth/pin-users/", views.pin_users),
    path("auth/refresh/", TokenRefreshView.as_view()),
    path("auth/me/", views.me),
    path("auth/verify-approval/", views.verify_approval),
    path("", include(router.urls)),
]
