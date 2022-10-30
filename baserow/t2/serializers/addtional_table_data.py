from baserow.contrib.database.api.tables.serializers import TableSerializer
from baserow.t2.models import AdditionalTableData
from rest_framework import serializers

class AdditionalTableDataSerializer(serializers.ModelSerializer):
    table =TableSerializer(read_only=True)
    class Meta:
        model = AdditionalTableData
        fields='__all__'