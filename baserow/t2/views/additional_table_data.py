
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from baserow.core.models import Group
from baserow.t2.models import AdditionalTableData
from baserow.t2.serializers.addtional_table_data import AdditionalTableDataSerializer


class AdditionalTableDataView(ModelViewSet):
    serializer_class = AdditionalTableDataSerializer
    pagination_class = LimitOffsetPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return AdditionalTableData.objects.filter(table__database__group__in=Group.objects.filter(users=self.request.user)).exclude(table__trashed=True).order_by('-id')
