from django.contrib.auth import get_user_model
from rest_framework.viewsets import ModelViewSet

from baserow.api.pagination import PageNumberPagination
from baserow.t2.permission import IsStaff
from baserow.t2.serializers.staff_control import StaffUserControlSerializer


class StaffUserControlViewSet(ModelViewSet):
    serializer_class = StaffUserControlSerializer
    permission_classes = [IsStaff]

    def get_queryset(self):
        return get_user_model().objects.all().order_by('-id')