from rest_framework import serializers

from baserow.api.user.serializers import UserSerializer
from baserow.api.utils import get_serializer_class
from baserow.contrib.database.fields.models import Field, LinkRowField
from baserow.contrib.database.table.models import Table
from baserow.core.action.models import Action


class FieldActionLogSerializer(serializers.ModelSerializer):
    user = UserSerializer()
    params = serializers.SerializerMethodField()

    @staticmethod
    def find_reversed_link_row(t_id, r_id, filed):
        table = Table.objects.get(id=t_id).get_model()
        row = table.objects.get(id=r_id)
        related_items = getattr(row, filed).all()
        if related_items :
            return related_items, str(related_items.first()._meta.model).split('Table')[1].split('Model')[0]
        else:
            return None,None

    @staticmethod
    def find_serializer_field(table):
        fields = ['id'] + [f'field_{f.id}' for f in Field.objects.filter(table=table, primary=True)]
        return fields

    def get_params(self, obj):

        new_row_values = obj.params.get('new_row_values')
        old_row_values = obj.params.get('original_row_values')
        if new_row_values:
            new_values = self.re_serializer_nested_row(new_row_values)
            obj.params.update({'new_row_values': new_values})
        if old_row_values:
            new_values = self.re_serializer_nested_row(old_row_values)
            obj.params.update({'original_row_values': new_values})

        return obj.params

    def re_serializer_nested_row(self, values):
        replaced_new_values = {}
        for k, v in values.items():
            is_link_row = bool(LinkRowField.objects.filter(id=k.split('_')[1]))
            table_param = self.context['request'].query_params.get('table')
            row_param = self.context['request'].query_params.get('row')
            if  v and isinstance(v, list) and all([type(i) is int for i in v]) and is_link_row and table_param and row_param:
                reversed_link_row, reverse_table_id = self.find_reversed_link_row(table_param, row_param, k)
                if reversed_link_row and  reverse_table_id:
                    table = Table.objects.get(id=reverse_table_id)
                    model = table.get_model()
                    field_to_serialize = self.find_serializer_field(table)
                    serialized_date = get_serializer_class(model, field_to_serialize)(reversed_link_row, many=True).data
                    replaced_new_values[k] = serialized_date
                else:
                    replaced_new_values[k] = v
            else:
                replaced_new_values[k] = v
        return replaced_new_values

    class Meta:
        fields = '__all__'
        model = Action
