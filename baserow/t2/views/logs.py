from rest_framework.generics import ListAPIView
from baserow.core.models import Action
from baserow.t2.serializers.log_serializer import FieldActionLogSerializer


from django_filters import rest_framework as filters

from baserow.t2.filters import ModelContainJsonFilter


class FieldActionLogsView(ListAPIView):
    permission_classes = []
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = ModelContainJsonFilter
    queryset = Action.objects.filter(type="update_row")#,params__new_row_values__has_key="field_192")
    serializer_class =FieldActionLogSerializer