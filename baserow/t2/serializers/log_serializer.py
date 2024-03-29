from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

from baserow.api.user.serializers import UserSerializer
from baserow.api.utils import get_serializer_class
from baserow.contrib.database.fields.models import Field, LinkRowField, SelectOption
from baserow.contrib.database.table.models import Table
from baserow.core.action.models import Action


class FieldActionLogSerializer(serializers.ModelSerializer):
    user = UserSerializer()
    params = serializers.SerializerMethodField()
    created_on=serializers.DateTimeField()
    action_type=serializers.CharField(source='type')

    @staticmethod
    def find_reversed_link_row(t_id, r_id, v, k):
        print("inside")
        print(t_id)
        print(r_id)
        print(v)
        print(k)
        table = Table.objects.get(id=t_id).get_model()
        row = table.objects.get(id=r_id)
        related_model = getattr(row, k).model

        #if here to change all related_model and v=

        related_items = related_model.objects.filter(id__in=v)  # getattr(row, filed).all()
        if related_items and related_model:
            table_id = str(related_model).split('Table')[1].split('Model')[0]
            primary_field = Field.objects.get(table_id=table_id, primary=True)
            if table_id and primary_field.content_type.model=='linkrowfield':
                related_model = getattr(related_model.objects.get(id=related_items.first().id),f'{primary_field.db_column}').model
                related_items=related_model.objects.filter(id__in=related_items.values(f'{primary_field.db_column}'))
                table_id = str(related_model).split('Table')[1].split('Model')[0]

            return related_items, related_model, table_id
        else:
            return None, None ,None

    @staticmethod
    def find_serializer_field(table):
        fields = ['id'] + [f'field_{f.id}' for f in Field.objects.filter(table=table, primary=True)]
        return fields

    def get_params(self, obj):

        new_row_values = obj.params.get('new_row_values', None)
        original_row_values = obj.params.get('original_row_values', None)
        new_rows =obj.params.get('new_rows', None)
        if original_row_values:
            original_row_values_serialized = self.re_serializer_nested_row(original_row_values)
            obj.params.update({'original_row_values': original_row_values_serialized})
        if new_row_values:
            new_row_values_serialized = self.re_serializer_nested_row(new_row_values)
            obj.params.update({'new_row_values': new_row_values_serialized})
        #
        return obj.params

    def re_serializer_nested_row(self, values):
        replaced_new_values = {}
        for k, v in values.items():
            is_link_row = k != "id" and bool(LinkRowField.objects.filter(id=k.split('_')[1]))
            is_multi_or_single_choice= k != "id"  and bool(SelectOption.objects.filter(field_id=k.split('_')[1]))
            table_param = self.context['request'].query_params.get('table')
            row_param = self.context['request'].query_params.get('row')
            print(v)
            if v and isinstance(v, list) and all(
                    [type(i) is int for i in v]) and is_link_row and table_param and row_param:
                related_items, related_model, table_id = self.find_reversed_link_row(table_param, row_param, v, k)
                if related_items and related_model:
                    field_to_serialize = self.find_serializer_field(table_id)
                    serialized_date = get_serializer_class(related_model, field_to_serialize)(related_items,
                                                                                              many=True).data
                    #TODO may be here re serialize
                    replaced_new_values[k] = serialized_date
                else:
                    replaced_new_values[k] = v
            elif v and is_multi_or_single_choice and table_param and row_param:
                replaced_new_values[k] = [i.value for i in SelectOption.objects.filter(id__in=v if type(v) == list else [v])]

            else:
                replaced_new_values[k] = v
        return replaced_new_values

    class Meta:
        fields = '__all__'
        model = Action
