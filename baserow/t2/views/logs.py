from django_filters import rest_framework as filters
from rest_framework.generics import ListAPIView
from rest_framework.pagination import LimitOffsetPagination

from baserow.core.models import Action
from baserow.t2.filters import ModelContainJsonFilter
from baserow.t2.serializers.log_serializer import FieldActionLogSerializer


class FieldActionLogsView(ListAPIView):
    permission_classes = []
    pagination_class = LimitOffsetPagination
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = ModelContainJsonFilter
    queryset = Action.objects.filter(type__in=['update_rows','update_row','create_row','create_rows']).order_by('-id')  # ,params__new_row_values__has_key="field_192")
    serializer_class = FieldActionLogSerializer
