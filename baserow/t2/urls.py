from django.urls import path, re_path

from .models import AdditionalTableData
from .views.additional_table_data import AdditionalTableDataView
from .views.crunch_base import CrunchBaseOrganization, CrunchBaseFounder, CustomerRequestView, OrgFounderMapView, \
    GetLastId, LisTable, ListField, TableContent, CrunchBasePerson
from rest_framework.routers import DefaultRouter
from django.urls import include

from baserow.t2.views.logs import FieldActionLogsView
from baserow.t2.views.row_comments import RowCommentView
from baserow.t2.views.staff_users import StaffUserControlViewSet

router=DefaultRouter()
router.register('staff-control',StaffUserControlViewSet,basename='staff_control')
router.register('table-additional-data',AdditionalTableDataView,basename='table-additional-data')

from django.db import transaction
transaction.rollback()
app_name = "baserow.t2"

urlpatterns =[
    path('crunch_base_organization/<int:table_id>/<int:row_id>/',CrunchBaseOrganization.as_view()),
    path('crunch_base_founder/<int:table_id>/<int:row_id>/',CrunchBaseFounder.as_view()),
    path('crunch_base_person/<int:table_id>/<int:row_id>/',CrunchBasePerson.as_view()),
    path('',include(router.urls)),
    path( "row-comment/<int:table_id>/<int:row_id>/",RowCommentView.as_view(),name="item"),
    path( "field-logs/",FieldActionLogsView.as_view(),name="logs"),
    path( "customer-request/<int:request_id>/",CustomerRequestView.as_view(),name="logs"),
    path( "org-founder-map/<int:request_id>/",OrgFounderMapView.as_view(),name="logs"),
    path( "list-tabels/",LisTable.as_view(),name="tables"),
    path( "list-fields/",ListField.as_view(),name="fields"),
    path( "get-table-content/<int:table_id>/",TableContent.as_view(),name="content"),
    path("get-last-id/<int:table_id>/<int:field_id>/", GetLastId.as_view(), name="last_id"),

]