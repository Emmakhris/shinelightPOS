from django.urls import path

from . import views

urlpatterns = [
    path("momo/", views.momo),
    path("momo/<str:reference>/", views.momo_detail),
    path("momo/<str:reference>/otp/", views.momo_otp),
    path("momo/<str:reference>/cancel/", views.momo_cancel),
    path("momo/<str:reference>/refund/", views.momo_refund),
    path("refunds/", views.refunds),
    path("refunds/<str:reference>/check/", views.refund_check),
    path("refunds/<str:reference>/retry/", views.refund_retry),
    path("refunds/<str:reference>/settle/", views.refund_settle),
    path("paystack/webhook/", views.webhook),
]
