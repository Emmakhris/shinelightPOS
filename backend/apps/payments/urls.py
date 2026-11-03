from django.urls import path

from . import views

urlpatterns = [
    path("momo/", views.momo),
    path("momo/<str:reference>/", views.momo_detail),
    path("momo/<str:reference>/otp/", views.momo_otp),
    path("momo/<str:reference>/cancel/", views.momo_cancel),
    path("paystack/webhook/", views.webhook),
]
