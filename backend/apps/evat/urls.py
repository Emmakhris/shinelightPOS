from django.urls import path

from . import views

urlpatterns = [
    path("", views.overview),
    path("send/", views.send),
]
