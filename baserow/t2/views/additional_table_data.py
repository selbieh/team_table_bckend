from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from baserow.t2.models import AdditionalTableData
from baserow.t2.serializers.addtional_table_data import AdditionalTableDataSerializer


class AdditionalTableDataView(ModelViewSet):
    queryset = AdditionalTableData.objects.exclude(trashed=True).order_by('-id')
    serializer_class = AdditionalTableDataSerializer
    pagination_class = LimitOffsetPagination
    permission_classes = [IsAuthenticated]
