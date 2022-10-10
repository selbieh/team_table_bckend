from django_filters import rest_framework as filters
from rest_framework.generics import ListAPIView

from baserow.core.models import Action
from baserow.t2.filters import ModelContainJsonFilter
from baserow.t2.serializers.log_serializer import FieldActionLogSerializer


class FieldActionLogsView(ListAPIView):
    permission_classes = []
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = ModelContainJsonFilter
    queryset = Action.objects.filter(type="update_row").order_by('-id')  # ,params__new_row_values__has_key="field_192")
    serializer_class = FieldActionLogSerializer
