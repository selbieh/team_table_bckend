from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from django.conf import settings
from baserow.core.models import Group,GroupUser


class StaffUserControlSerializer(serializers.ModelSerializer):
    is_active=serializers.BooleanField(default=True)
    password=serializers.CharField(write_only=True)

    class Meta:
        model = get_user_model()
        exclude =('last_login','is_staff','date_joined','groups')

    def get_tribal_group(self):
        try:
            tribal_group =Group.objects.get(name=settings.TRIBAL_GROUP_NAME)
        except:
            raise serializers.ValidationError(detail='tribal group not found or not named same to settings.TRIBAL_GROUP')
        return tribal_group

    def create(self,validated_data):
        with transaction.atomic():
            try:
                user=super(StaffUserControlSerializer, self).create(validated_data)
                user.set_password(validated_data['password'])
                user.save()
                GroupUser.objects.create(user=user,group=self.get_tribal_group(),permissions='ADMIN',order=1)
                return user
            except Exception as e:
                raise serializers.ValidationError(detail=e.args)

    def update(self, instance, validated_data):
        super(StaffUserControlSerializer, self).update(instance, validated_data)
        if validated_data['password']:
            instance.set_password(validated_data['password'])
            instance.save()
        return instance
