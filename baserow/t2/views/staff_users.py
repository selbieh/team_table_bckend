from django.contrib.auth import get_user_model
from rest_framework.viewsets import ModelViewSet
from rest_framework_jwt.permissions import IsSuperUser

from api.pagination import PageNumberPagination
from t2.serializers.staff_control import StaffUserControlSerializer


class StaffUserControlViewSet(ModelViewSet):
    serializer_class = StaffUserControlSerializer
    permission_classes = [IsSuperUser]

    def get_queryset(self):
        return get_user_model().objects.all()