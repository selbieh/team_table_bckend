from django.db.models import Q
from django_filters import rest_framework as filters

from baserow.core.action.models import Action


class ModelContainJsonFilter(filters.FilterSet):
    table=filters.NumberFilter(method='get_table')
    field = filters.NumberFilter(method='get_field')
    row=filters.NumberFilter(method='get_row')

    def get_table(self, queryset, name, value):
        if name and value:
            return queryset.filter(scope=f'table{value}').filter(params__table_id=int(value))
        return queryset
    def get_field(self,queryset,name,value):

        if name and value:
            return queryset.filter(Q(params__new_row_values__has_key=int(value)) | Q (params__row_ids__contains=value))
        return queryset
    def get_row(self,queryset,name,value):

        if name and value:
            return queryset.filter(params__row_id=int(value))
        return queryset

    class Meta:
        model = Action
        fields = ['field','table','row']
