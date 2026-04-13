from rest_framework.pagination import PageNumberPagination


class OptionalPageNumberPagination(PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 100

    def paginate_queryset(self, queryset, request, view=None):
        has_page_request = "page" in request.query_params or "page_size" in request.query_params
        if not has_page_request:
            return None
        return super().paginate_queryset(queryset, request, view=view)
