from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import TemplateView
from django.views.static import serve

api_patterns = [
    path("", include("apps.accounts.urls")),
    path("", include("apps.business.urls")),
    path("catalog/", include("apps.catalog.urls")),
    path("inventory/", include("apps.inventory.urls")),
    path("customers/", include("apps.customers.urls")),
    path("shifts/", include("apps.shifts.urls")),
    path("sales/", include("apps.sales.urls")),
    path("restaurant/", include("apps.restaurant.urls")),
    path("reports/", include("apps.reports.urls")),
    path("payments/", include("apps.payments.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(api_patterns)),
    # Product images and logos. A single-business local install serves them directly.
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]

if (settings.FRONTEND_DIST / "index.html").exists():
    # Client-side routes (/pos, /sales/12 ...) all load the React app.
    urlpatterns.append(
        re_path(r"^(?!api/|admin/|media/|static/).*$", TemplateView.as_view(template_name="index.html"))
    )
