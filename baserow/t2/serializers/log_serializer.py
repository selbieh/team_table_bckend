from rest_framework import serializers

from api.user.serializers import UserSerializer
from baserow.core.action.models import Action


class FieldActionLogSerializer(serializers.ModelSerializer):
    user=UserSerializer()
    class Meta:
        fields='__all__'
        model = Action
