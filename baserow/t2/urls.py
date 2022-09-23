from django.urls import path, re_path

from .views.crunch_base import CrunchBaseOrganization, CrunchBaseFounder
from rest_framework.routers import DefaultRouter
from django.urls import include

from baserow.t2.views.logs import FieldActionLogsView
from baserow.t2.views.row_comments import RowCommentView
from baserow.t2.views.staff_users import StaffUserControlViewSet

router=DefaultRouter()
router.register('staff-control',StaffUserControlViewSet,basename='staff_control')


app_name = "baserow.t2"

urlpatterns =[
    path('crunch_base_organization/<int:table_id>/<int:row_id>/',CrunchBaseOrganization.as_view()),
    path('crunch_base_founder/<int:table_id>/<int:row_id>/',CrunchBaseFounder.as_view()),
    path('',include(router.urls)),
    path( "row-comment/<int:table_id>/<int:row_id>/",RowCommentView.as_view(),name="item"),
    path( "field-logs/",FieldActionLogsView.as_view(),name="logs"),
]