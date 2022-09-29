from django_filters import rest_framework as filters

from baserow.core.action.models import Action


class ModelContainJsonFilter(filters.FilterSet):
    field = filters.CharFilter(method='get_field')
    row=filters.CharFilter(method='get_row')
    table=filters.CharFilter(method='get_table')
    def get_field(self,queryset,name,value):

        if name and value:
            return queryset.filter(params__new_row_values__has_key=value)
        return queryset
    def get_row(self,queryset,name,value):

        if name and value:
            return queryset.filter(params__row_id=value)
        return queryset
    def get_table(self,queryset,name,value):

        if name and value:
            return queryset.filter(params__table_id=value)
        return queryset
    class Meta:
        model = Action
        fields = ['field','table','row']
