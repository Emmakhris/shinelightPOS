from rest_framework.pagination import PageNumberPagination


class OptionalPagination(PageNumberPagination):
    """Paginate only when the client asks with ?page=; POS lookups usually want the full list."""

    page_size_query_param = "page_size"
    max_page_size = 500

    def paginate_queryset(self, queryset, request, view=None):
        if "page" not in request.query_params:
            return None
        return super().paginate_queryset(queryset, request, view)
