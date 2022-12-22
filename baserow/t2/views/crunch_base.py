import datetime
import json
from collections.abc import Iterable

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.decorators import permission_classes
from rest_framework.generics import RetrieveAPIView, ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from baserow.api.decorators import map_exceptions
from baserow.api.errors import ERROR_USER_NOT_IN_GROUP
from baserow.api.exceptions import RequestBodyValidationException
from baserow.api.schemas import get_error_schema, CLIENT_SESSION_ID_SCHEMA_PARAMETER
from baserow.api.user_files.errors import ERROR_USER_FILE_DOES_NOT_EXIST
from baserow.api.utils import validate_data
from baserow.contrib.database.api.fields.errors import ERROR_INVALID_SELECT_OPTION_VALUES
from baserow.contrib.database.api.fields.serializers import FieldSerializer
from baserow.contrib.database.api.rows.errors import ERROR_ROW_DOES_NOT_EXIST
from baserow.contrib.database.api.rows.serializers import get_row_serializer_class, RowSerializer, \
    get_example_row_serializer_class
from baserow.contrib.database.api.tables.errors import ERROR_TABLE_DOES_NOT_EXIST
from baserow.contrib.database.api.tables.serializers import TableSerializer
from baserow.contrib.database.api.tokens.authentications import TokenAuthentication
from baserow.contrib.database.api.tokens.errors import ERROR_NO_PERMISSION_TO_TABLE
from baserow.contrib.database.fields.exceptions import AllProvidedMultipleSelectValuesMustBeSelectOption
from baserow.contrib.database.fields.models import Field
from baserow.contrib.database.models import Database
from baserow.contrib.database.rows.actions import UpdateRowActionType
from baserow.contrib.database.rows.exceptions import RowDoesNotExist
from baserow.contrib.database.rows.handler import RowHandler
from baserow.contrib.database.table.exceptions import TableDoesNotExist
from baserow.contrib.database.table.handler import TableHandler
from baserow.contrib.database.table.models import Table
from baserow.contrib.database.tokens.exceptions import NoPermissionToTable
from baserow.contrib.database.tokens.handler import TokenHandler
from baserow.core.action.registries import action_type_registry
from baserow.core.exceptions import UserNotInGroup
from baserow.core.models import Group
from baserow.core.user_files.exceptions import UserFileDoesNotExist
from baserow.t2.errors import ERROR_CB_URL_NOT_EXIST, ERROR_ORG_OF_INTEREST_CB_URL_NOT_EXIST
from baserow.t2.exceptions import CbUrlDoesNotExist, OrgOfInterestCBURLNotExist
from baserow.t2.models.CrunchBaseLogs import CrunchBaseLogs
from baserow.t2.serializers.crunch_base import CrunchBaseOrganizationSerializer, CrunchBaseFounderSerializer, \
    CrunchBasePersonSerializer


class CrunchBaseOrganization(APIView):
    authentication_classes = APIView.authentication_classes + [TokenAuthentication]
    permission_classes = (IsAuthenticated,)

    @map_exceptions(
        {
            UserNotInGroup: ERROR_USER_NOT_IN_GROUP,
            TableDoesNotExist: ERROR_TABLE_DOES_NOT_EXIST,
            RowDoesNotExist: ERROR_ROW_DOES_NOT_EXIST,
            NoPermissionToTable: ERROR_NO_PERMISSION_TO_TABLE,
            CbUrlDoesNotExist: ERROR_CB_URL_NOT_EXIST,
            OrgOfInterestCBURLNotExist: ERROR_ORG_OF_INTEREST_CB_URL_NOT_EXIST

        }
    )
    def post(self, request, table_id, row_id):
        """
        cb means crunch base,
        """

        table = TableHandler().get_table(table_id)
        TokenHandler().check_table_permissions(request, "read", table, False)
        model = table.get_model()
        row = RowHandler().get_row(request.user, table, row_id, model)
        serializer = CrunchBaseOrganizationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cb_url_field_name = serializer.validated_data['cb_url_field_name']
        cb_url_field_value = getattr(row, cb_url_field_name)
        if not cb_url_field_value:
            raise CbUrlDoesNotExist
        permalink = self.get_cb_url(request, cb_url_field_value)
        cb_call_response = self.call_cb(request, permalink)
        request.data.clear()
        request.data.update(self.map_cb_response_to_request_data(cb_call_response, serializer.validated_data))
        return self.patch_item(request, table_id, row_id)




    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="table_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="Updates the row in the table related to the value.",
            ),
            OpenApiParameter(
                name="row_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="Updates the row related to the value.",
            ),
            OpenApiParameter(
                name="user_field_names",
                location=OpenApiParameter.QUERY,
                type=OpenApiTypes.BOOL,
                description=(
                        "A flag query parameter which if provided this endpoint will "
                        "expect and return the user specified field names instead of "
                        "internal Baserow field names (field_123 etc)."
                ),
            ),
            CLIENT_SESSION_ID_SCHEMA_PARAMETER,
        ],
        tags=["Database table rows"],
        operation_id="update_database_table_row",
        description=(
                "Updates an existing row in the table if the user has access to the "
                "related table's group. The accepted body fields are depending on the "
                "fields that the table has. For a complete overview of fields use the "
                "**list_database_table_fields** endpoint to list them all. None of the "
                "fields are required, if they are not provided the value is not going to "
                "be updated. "
                "When you want to update a value for the field with id `10`, the key must "
                "be named `field_10`. Or if the GET parameter `user_field_names` is "
                "provided the key of the field to update must be the name of the field. "
                "Multiple different fields to update can be provided in one request. In "
                "the examples below you will find all the different field types, the "
                "numbers/ids in the example are just there for example purposes, "
                "the field_ID must be replaced with the actual id of the field or the name "
                "of the field if `user_field_names` is provided."
        ),
        request=get_example_row_serializer_class(
            example_type="patch", user_field_names=True
        ),
        responses={
            200: get_example_row_serializer_class(
                example_type="get", user_field_names=True
            ),
            400: get_error_schema(
                [
                    "ERROR_USER_NOT_IN_GROUP",
                    "ERROR_REQUEST_BODY_VALIDATION",
                    "ERROR_INVALID_SELECT_OPTION_VALUES",
                ]
            ),
            401: get_error_schema(["ERROR_NO_PERMISSION_TO_TABLE"]),
            404: get_error_schema(
                ["ERROR_TABLE_DOES_NOT_EXIST", "ERROR_ROW_DOES_NOT_EXIST"]
            ),
        },
    )
    @transaction.atomic
    @map_exceptions(
        {
            UserNotInGroup: ERROR_USER_NOT_IN_GROUP,
            TableDoesNotExist: ERROR_TABLE_DOES_NOT_EXIST,
            RowDoesNotExist: ERROR_ROW_DOES_NOT_EXIST,
            AllProvidedMultipleSelectValuesMustBeSelectOption: ERROR_INVALID_SELECT_OPTION_VALUES,
            NoPermissionToTable: ERROR_NO_PERMISSION_TO_TABLE,
            UserFileDoesNotExist: ERROR_USER_FILE_DOES_NOT_EXIST,
            CbUrlDoesNotExist: ERROR_CB_URL_NOT_EXIST,
            OrgOfInterestCBURLNotExist: ERROR_ORG_OF_INTEREST_CB_URL_NOT_EXIST

        }
    )
    def patch_item(self, request: Request, table_id: int, row_id: int) -> Response:
        """
        Updates the row with the given row_id for the table with the given
        table_id. Also the post data is validated according to the tables field types.

        :param request: The request object
        :param table_id: The id of the table to update the row in
        :param row_id: The id of the row to update
        :return: The updated row values serialized as a json object
        """
        table = TableHandler().get_table(table_id)
        TokenHandler().check_table_permissions(request, "update", table, False)

        user_field_names = "user_field_names" in request.GET
        field_ids, field_names = None, None
        if user_field_names:
            field_names = request.data.keys()
        else:
            field_ids = RowHandler().extract_field_ids_from_dict(request.data)
        model = table.get_model()
        validation_serializer = get_row_serializer_class(
            model,
            field_ids=field_ids,
            field_names_to_include=field_names,
            user_field_names=user_field_names,
        )
        data = validate_data(validation_serializer, request.data)
        try:
            row = action_type_registry.get_by_type(UpdateRowActionType).do(
                request.user,
                table,
                row_id,
                data,
                model=model,
                user_field_names=user_field_names,
            )
        except ValidationError as exc:
            raise RequestBodyValidationException(detail=exc.message) from exc

        serializer_class = get_row_serializer_class(
            model, RowSerializer, is_response=True, user_field_names=user_field_names
        )
        serializer = serializer_class(row)
        return Response(serializer.data)

    def get_cb_url(self, request, cb_field_value):
        try:
            cb_url = cb_field_value.replace('#/entity', '').split('/')[-1]
            return cb_url
        except:
            raise CbUrlDoesNotExist

    def call_cb(self, request, cb_permalink):
        baseurl = f"https://api.crunchbase.com/api/v4/entities/organizations/{cb_permalink}"
        url = f'{baseurl}?card_ids=fields&user_key={settings.CB_KEY}'  ###--->>['cards']['funding_total']
        response = requests.request("GET", url)
        if not response.status_code ==200:
            raise CbUrlDoesNotExist
        CrunchBaseLogs.objects.create(url=baseurl, response=response.json(), entity_type=CrunchBaseLogs.ORGANIZATION)
        return response.json()

    def map_cb_response_to_request_data(self, cb_call_response, validated_data):
        return {
            validated_data['cb_uuid_field_name']: cb_call_response['properties']['identifier']['uuid'],
            validated_data['company_total_raised_value_field_name']:
                cb_call_response.get('cards', {}).get('fields', {}).get('funding_total', {}).get('value', 0)
        }


class CrunchBaseFounder(APIView):
    authentication_classes = APIView.authentication_classes + [TokenAuthentication]
    permission_classes = []  # (IsAuthenticated,)

    @map_exceptions(
        {
            UserNotInGroup: ERROR_USER_NOT_IN_GROUP,
            TableDoesNotExist: ERROR_TABLE_DOES_NOT_EXIST,
            RowDoesNotExist: ERROR_ROW_DOES_NOT_EXIST,
            NoPermissionToTable: ERROR_NO_PERMISSION_TO_TABLE,
            CbUrlDoesNotExist: ERROR_CB_URL_NOT_EXIST,
            OrgOfInterestCBURLNotExist: ERROR_ORG_OF_INTEREST_CB_URL_NOT_EXIST

        }
    )
    def post(self, request, table_id, row_id):
        """
        cb means crunch base,
        ?participated_funding_rounds
        ?founded_organizations,
        """

        table = TableHandler().get_table(table_id)
        TokenHandler().check_table_permissions(request, "read", table, False)
        model = table.get_model()
        row = RowHandler().get_row(request.user, table, row_id, model)
        serializer = CrunchBaseFounderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cb_url_field_name = serializer.validated_data['cb_url_field_name']
        org_of_interest_cb_url=self.validate_org_of_interest_cb_url(row,serializer.validated_data)
        org_of_interest_cb_permalink=self.get_cb_url(request,org_of_interest_cb_url)
        cb_url_field_value = getattr(row, cb_url_field_name)
        if not cb_url_field_value or not isinstance(cb_url_field_value, Iterable) or not cb_url_field_value[0]['value']:
            raise CbUrlDoesNotExist
        try:
            cb_url_field_value = cb_url_field_value[0]['value']
        except:
            raise CbUrlDoesNotExist
        permalink = self.get_cb_url(request, cb_url_field_value)
        cb_call_response = self.call_cb(request, permalink)
        given_date = self.given_date(request, serializer.validated_data, row)
        #company_of_interest = self.get_company_of_interest(request, serializer.validated_data, row)
        filterd_response = self.filter_response(cb_call_response, given_date, [org_of_interest_cb_permalink])
        calculated_filtered_response = self.calculate_resulte_for_filtered_response(request, filterd_response)
        raise_count, raised_values = calculated_filtered_response
        request.data.clear()
        cb__uuid4=cb_call_response.get('properties',{}).get("identifier",{}).get('uuid')
        request.data.update(self.map_data(request, serializer.validated_data, raise_count, raised_values,cb__uuid4))
        return self.patch_item(request, table_id, row_id)
        # TODO map_resonse_and_save_in patch call
        # request.data.clear()
        # request.data.update(self.map_cb_response_to_request_data(cb_call_response, serializer.validated_data))
        # return self.patch_item(request, table_id, row_id)

    def validate_org_of_interest_cb_url(self, row, validated_data):
        row_value=getattr(row, validated_data.get('organization_of_interest_link_table')).all().first()
        if not row_value:
            raise OrgOfInterestCBURLNotExist
        organization_of_interest_from_org_founder_map_value=getattr(row_value,validated_data.get('organization_of_interest_from_org_founder_map')).all().first()
        if not organization_of_interest_from_org_founder_map_value:
            raise OrgOfInterestCBURLNotExist
        org_of_interest_cb_url=getattr(organization_of_interest_from_org_founder_map_value,validated_data.get('organization_of_interest_cb_link'))
        if not org_of_interest_cb_url:
            raise OrgOfInterestCBURLNotExist
        return org_of_interest_cb_url

        #organization_of_interest_cb_link

    # def get_company_of_interest(self, request, validated_data, row):
    #     org_of_interest_uuid = []
    #     column_value=getattr(row,validated_data.get('organization_of_interest_link_table')).all()
    #     if column_value:
    #         field_query_string=f'{validated_data.get("organization_of_interest_from_org_founder_map")}__'+f'{validated_data.get("organization_of_interest_cb_link")}'
    #         org_of_interest_uuid=list(set(column_value.values_list(field_query_string,flat=True)))
    #     return org_of_interest_uuid

    def get_cb_url(self, request, cb_field_value):
        try:
            cb_url = cb_field_value.replace('#/entity', '').split('/')[-1]
            return cb_url
        except:
            raise CbUrlDoesNotExist

    def filter_response(self, response, given_date, company_of_interest):
        filtered_response = []
        if isinstance(response, list):
            raise serializers.ValidationError(detail=f'{response}')
        all_founded_organizations = response.get('cards', {}).get('founded_organizations', [])
        filtered_founded_organizations_by_type = [item for item in all_founded_organizations if
                                                  'company_type' in item.keys() and item[
                                                      'company_type'] == 'for_profit' and item.get('properties', {}).get('identifier', {}).get('permalink',None) not in company_of_interest]

        # this step to exclude the org of intreset
        # filtered_founded_organizations_by_type_and_interest = [item for item in filtered_founded_organizations_by_type if
        #                                           ]
        for i in filtered_founded_organizations_by_type:
            company_founded_year = i.get('founded_on') or None
            # company with missing founded year or founded year <= date
            if not company_founded_year or (company_founded_year['precision'] == 'year' and datetime.datetime.strptime(
                    company_founded_year['value'], '%Y-%m-%d').date().year < given_date.year):
                filtered_response.append(i)
            elif datetime.datetime.strptime(company_founded_year['value'], '%Y-%m-%d').date() < given_date:
                filtered_response.append(i)
        return filtered_response

    def call_cb(self, request, cb_permalink):
        baseurl = f"https://api.crunchbase.com/api/v4/entities/people/{cb_permalink}"
        url = f'{baseurl}?card_ids=founded_organizations&user_key={settings.CB_KEY}'
        response = requests.request("GET", url)
        if not response.status_code ==200:
            raise CbUrlDoesNotExist
        CrunchBaseLogs.objects.create(url=baseurl, response=response.json(), entity_type=CrunchBaseLogs.FOUNDER)
        return response.json()

    def given_date(self, request, validated_data, row):
        now_data = datetime.date.today()
        try:
            org_of_interest = getattr(getattr(row, validated_data['organization_of_interest_field_name']).all().first(),
                                      validated_data['org_founder_map_founding_date_field_name'])
            if not org_of_interest:
                return now_data
            x = datetime.datetime.strptime(org_of_interest, '%B %m, %Y')
            return x.date()
        except:
            return now_data

    def calculate_resulte_for_filtered_response(self, request, filtered_response):
        total_value_list = []
        count = 0
        for company in filtered_response:
            baseurl = f"https://api.crunchbase.com/api/v4/entities/organizations/{company['identifier']['uuid']}"
            url = f'{baseurl}?card_ids=fields&user_key={settings.CB_KEY}'
            company_response = requests.get(url)#.json()
            if not company_response.status_code == 200:
                raise CbUrlDoesNotExist
            company_response = requests.get(url).json()
            company_raised_value = company_response.get('cards', {}).get('fields', {}).get('funding_total', {}).get(
                'value', 0)
            if company_raised_value:
                total_value_list.append(company_raised_value)
                count += 1
        return count, sum(total_value_list)

    def map_data(self, request, validated_data, raise_count, raised_values,cb__uuid4):
        return {
            validated_data['company_prev_raised_count_field_name']: raise_count,
            validated_data['company_total_raised_value_field_name']: raised_values,
            validated_data['cb_uuid_field_name']:cb__uuid4
        }

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="table_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="Updates the row in the table related to the value.",
            ),
            OpenApiParameter(
                name="row_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="Updates the row related to the value.",
            ),
            OpenApiParameter(
                name="user_field_names",
                location=OpenApiParameter.QUERY,
                type=OpenApiTypes.BOOL,
                description=(
                        "A flag query parameter which if provided this endpoint will "
                        "expect and return the user specified field names instead of "
                        "internal Baserow field names (field_123 etc)."
                ),
            ),
            CLIENT_SESSION_ID_SCHEMA_PARAMETER,
        ],
        tags=["Database table rows"],
        operation_id="update_database_table_row",
        description=(
                "Updates an existing row in the table if the user has access to the "
                "related table's group. The accepted body fields are depending on the "
                "fields that the table has. For a complete overview of fields use the "
                "**list_database_table_fields** endpoint to list them all. None of the "
                "fields are required, if they are not provided the value is not going to "
                "be updated. "
                "When you want to update a value for the field with id `10`, the key must "
                "be named `field_10`. Or if the GET parameter `user_field_names` is "
                "provided the key of the field to update must be the name of the field. "
                "Multiple different fields to update can be provided in one request. In "
                "the examples below you will find all the different field types, the "
                "numbers/ids in the example are just there for example purposes, "
                "the field_ID must be replaced with the actual id of the field or the name "
                "of the field if `user_field_names` is provided."
        ),
        request=get_example_row_serializer_class(
            example_type="patch", user_field_names=True
        ),
        responses={
            200: get_example_row_serializer_class(
                example_type="get", user_field_names=True
            ),
            400: get_error_schema(
                [
                    "ERROR_USER_NOT_IN_GROUP",
                    "ERROR_REQUEST_BODY_VALIDATION",
                    "ERROR_INVALID_SELECT_OPTION_VALUES",
                ]
            ),
            401: get_error_schema(["ERROR_NO_PERMISSION_TO_TABLE"]),
            404: get_error_schema(
                ["ERROR_TABLE_DOES_NOT_EXIST", "ERROR_ROW_DOES_NOT_EXIST"]
            ),
        },
    )
    @transaction.atomic
    @map_exceptions(
        {
            UserNotInGroup: ERROR_USER_NOT_IN_GROUP,
            TableDoesNotExist: ERROR_TABLE_DOES_NOT_EXIST,
            RowDoesNotExist: ERROR_ROW_DOES_NOT_EXIST,
            AllProvidedMultipleSelectValuesMustBeSelectOption: ERROR_INVALID_SELECT_OPTION_VALUES,
            NoPermissionToTable: ERROR_NO_PERMISSION_TO_TABLE,
            UserFileDoesNotExist: ERROR_USER_FILE_DOES_NOT_EXIST,
            CbUrlDoesNotExist: ERROR_CB_URL_NOT_EXIST,
            OrgOfInterestCBURLNotExist: ERROR_ORG_OF_INTEREST_CB_URL_NOT_EXIST
        }
    )
    def patch_item(self, request: Request, table_id: int, row_id: int) -> Response:
        """
        Updates the row with the given row_id for the table with the given
        table_id. Also the post data is validated according to the tables field types.

        :param request: The request object
        :param table_id: The id of the table to update the row in
        :param row_id: The id of the row to update
        :return: The updated row values serialized as a json object
        """
        table = TableHandler().get_table(table_id)
        TokenHandler().check_table_permissions(request, "update", table, False)

        user_field_names = "user_field_names" in request.GET
        field_ids, field_names = None, None
        if user_field_names:
            field_names = request.data.keys()
        else:
            field_ids = RowHandler().extract_field_ids_from_dict(request.data)
        model = table.get_model()
        validation_serializer = get_row_serializer_class(
            model,
            field_ids=field_ids,
            field_names_to_include=field_names,
            user_field_names=user_field_names,
        )
        data = validate_data(validation_serializer, request.data)
        try:
            row = action_type_registry.get_by_type(UpdateRowActionType).do(
                request.user,
                table,
                row_id,
                data,
                model=model,
                user_field_names=user_field_names,
            )
        except ValidationError as exc:
            raise RequestBodyValidationException(detail=exc.message) from exc

        serializer_class = get_row_serializer_class(
            model, RowSerializer, is_response=True, user_field_names=user_field_names
        )
        serializer = serializer_class(row)
        return Response(serializer.data)

class CrunchBasePerson(APIView):
    authentication_classes = APIView.authentication_classes + [TokenAuthentication]
    permission_classes = []  # (IsAuthenticated,)

    @map_exceptions(
        {
            UserNotInGroup: ERROR_USER_NOT_IN_GROUP,
            TableDoesNotExist: ERROR_TABLE_DOES_NOT_EXIST,
            RowDoesNotExist: ERROR_ROW_DOES_NOT_EXIST,
            NoPermissionToTable: ERROR_NO_PERMISSION_TO_TABLE,
            CbUrlDoesNotExist: ERROR_CB_URL_NOT_EXIST,
            OrgOfInterestCBURLNotExist: ERROR_ORG_OF_INTEREST_CB_URL_NOT_EXIST

        }
    )
    def post(self, request, table_id, row_id):
        """
        cb means crunch base,
        ?participated_funding_rounds
        ?founded_organizations,
        """

        table = TableHandler().get_table(table_id)
        TokenHandler().check_table_permissions(request, "read", table, False)
        model = table.get_model()
        row = RowHandler().get_row(request.user, table, row_id, model)
        serializer = CrunchBasePersonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cb_url_field_name = serializer.validated_data['cb_url_field_name']
        cb_url_field_value = getattr(row, cb_url_field_name)
        if not cb_url_field_value:
            raise CbUrlDoesNotExist
        permalink = self.get_cb_url(request, cb_url_field_value)
        cb_call_response = self.call_cb(request, permalink)
        cb__uuid4=cb_call_response.get('properties',{}).get("identifier",{}).get('uuid')
        request.data.update(self.map_data(request, serializer.validated_data, cb__uuid4))
        return self.patch_item(request, table_id, row_id)
        # TODO map_resonse_and_save_in patch call
        # request.data.clear()
        # request.data.update(self.map_cb_response_to_request_data(cb_call_response, serializer.validated_data))
        # return self.patch_item(request, table_id, row_id)

    def validate_org_of_interest_cb_url(self, row, validated_data):
        row_value=getattr(row, validated_data.get('organization_of_interest_link_table')).all().first()
        if not row_value:
            raise OrgOfInterestCBURLNotExist
        organization_of_interest_from_org_founder_map_value=getattr(row_value,validated_data.get('organization_of_interest_from_org_founder_map')).all().first()
        if not organization_of_interest_from_org_founder_map_value:
            raise OrgOfInterestCBURLNotExist
        org_of_interest_cb_url=getattr(organization_of_interest_from_org_founder_map_value,validated_data.get('organization_of_interest_cb_link'))
        if not org_of_interest_cb_url:
            raise OrgOfInterestCBURLNotExist
        return org_of_interest_cb_url

        #organization_of_interest_cb_link

    # def get_company_of_interest(self, request, validated_data, row):
    #     org_of_interest_uuid = []
    #     column_value=getattr(row,validated_data.get('organization_of_interest_link_table')).all()
    #     if column_value:
    #         field_query_string=f'{validated_data.get("organization_of_interest_from_org_founder_map")}__'+f'{validated_data.get("organization_of_interest_cb_link")}'
    #         org_of_interest_uuid=list(set(column_value.values_list(field_query_string,flat=True)))
    #     return org_of_interest_uuid

    def get_cb_url(self, request, cb_field_value):
        try:
            cb_url = cb_field_value.replace('#/entity', '').split('/')[-1]
            return cb_url
        except:
            raise CbUrlDoesNotExist

    def filter_response(self, response, given_date, company_of_interest):
        filtered_response = []
        if isinstance(response, list):
            raise serializers.ValidationError(detail=f'{response}')
        all_founded_organizations = response.get('cards', {}).get('founded_organizations', [])
        filtered_founded_organizations_by_type = [item for item in all_founded_organizations if
                                                  'company_type' in item.keys() and item[
                                                      'company_type'] == 'for_profit' and item.get('properties', {}).get('identifier', {}).get('permalink',None) not in company_of_interest]

        # this step to exclude the org of intreset
        # filtered_founded_organizations_by_type_and_interest = [item for item in filtered_founded_organizations_by_type if
        #                                           ]
        for i in filtered_founded_organizations_by_type:
            company_founded_year = i.get('founded_on') or None
            # company with missing founded year or founded year <= date
            if not company_founded_year or (company_founded_year['precision'] == 'year' and datetime.datetime.strptime(
                    company_founded_year['value'], '%Y-%m-%d').date().year < given_date.year):
                filtered_response.append(i)
            elif datetime.datetime.strptime(company_founded_year['value'], '%Y-%m-%d').date() < given_date:
                filtered_response.append(i)
        return filtered_response

    def call_cb(self, request, cb_permalink):
        baseurl = f"https://api.crunchbase.com/api/v4/entities/people/{cb_permalink}"
        url = f'{baseurl}?card_ids=founded_organizations&user_key={settings.CB_KEY}'
        response = requests.request("GET", url)
        if not response.status_code ==200:
            raise CbUrlDoesNotExist
        CrunchBaseLogs.objects.create(url=baseurl, response=response.json(), entity_type=CrunchBaseLogs.FOUNDER)
        return response.json()

    def given_date(self, request, validated_data, row):
        now_data = datetime.date.today()
        try:
            org_of_interest = getattr(getattr(row, validated_data['organization_of_interest_field_name']).all().first(),
                                      validated_data['org_founder_map_founding_date_field_name'])
            if not org_of_interest:
                return now_data
            x = datetime.datetime.strptime(org_of_interest, '%B %m, %Y')
            return x.date()
        except:
            return now_data

    def calculate_resulte_for_filtered_response(self, request, filtered_response):
        total_value_list = []
        count = 0
        for company in filtered_response:
            baseurl = f"https://api.crunchbase.com/api/v4/entities/organizations/{company['identifier']['uuid']}"
            url = f'{baseurl}?card_ids=fields&user_key={settings.CB_KEY}'
            company_response = requests.get(url)#.json()
            if not company_response.status_code == 200:
                raise CbUrlDoesNotExist
            company_response = requests.get(url).json()
            company_raised_value = company_response.get('cards', {}).get('fields', {}).get('funding_total', {}).get(
                'value', 0)
            if company_raised_value:
                total_value_list.append(company_raised_value)
                count += 1
        return count, sum(total_value_list)

    def map_data(self, request, validated_data,cb__uuid4):
        return {

            validated_data['cb_uuid_field_name']:cb__uuid4
        }

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="table_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="Updates the row in the table related to the value.",
            ),
            OpenApiParameter(
                name="row_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="Updates the row related to the value.",
            ),
            OpenApiParameter(
                name="user_field_names",
                location=OpenApiParameter.QUERY,
                type=OpenApiTypes.BOOL,
                description=(
                        "A flag query parameter which if provided this endpoint will "
                        "expect and return the user specified field names instead of "
                        "internal Baserow field names (field_123 etc)."
                ),
            ),
            CLIENT_SESSION_ID_SCHEMA_PARAMETER,
        ],
        tags=["Database table rows"],
        operation_id="update_database_table_row",
        description=(
                "Updates an existing row in the table if the user has access to the "
                "related table's group. The accepted body fields are depending on the "
                "fields that the table has. For a complete overview of fields use the "
                "**list_database_table_fields** endpoint to list them all. None of the "
                "fields are required, if they are not provided the value is not going to "
                "be updated. "
                "When you want to update a value for the field with id `10`, the key must "
                "be named `field_10`. Or if the GET parameter `user_field_names` is "
                "provided the key of the field to update must be the name of the field. "
                "Multiple different fields to update can be provided in one request. In "
                "the examples below you will find all the different field types, the "
                "numbers/ids in the example are just there for example purposes, "
                "the field_ID must be replaced with the actual id of the field or the name "
                "of the field if `user_field_names` is provided."
        ),
        request=get_example_row_serializer_class(
            example_type="patch", user_field_names=True
        ),
        responses={
            200: get_example_row_serializer_class(
                example_type="get", user_field_names=True
            ),
            400: get_error_schema(
                [
                    "ERROR_USER_NOT_IN_GROUP",
                    "ERROR_REQUEST_BODY_VALIDATION",
                    "ERROR_INVALID_SELECT_OPTION_VALUES",
                ]
            ),
            401: get_error_schema(["ERROR_NO_PERMISSION_TO_TABLE"]),
            404: get_error_schema(
                ["ERROR_TABLE_DOES_NOT_EXIST", "ERROR_ROW_DOES_NOT_EXIST"]
            ),
        },
    )
    @transaction.atomic
    @map_exceptions(
        {
            UserNotInGroup: ERROR_USER_NOT_IN_GROUP,
            TableDoesNotExist: ERROR_TABLE_DOES_NOT_EXIST,
            RowDoesNotExist: ERROR_ROW_DOES_NOT_EXIST,
            AllProvidedMultipleSelectValuesMustBeSelectOption: ERROR_INVALID_SELECT_OPTION_VALUES,
            NoPermissionToTable: ERROR_NO_PERMISSION_TO_TABLE,
            UserFileDoesNotExist: ERROR_USER_FILE_DOES_NOT_EXIST,
            CbUrlDoesNotExist: ERROR_CB_URL_NOT_EXIST,
            OrgOfInterestCBURLNotExist: ERROR_ORG_OF_INTEREST_CB_URL_NOT_EXIST
        }
    )
    def patch_item(self, request: Request, table_id: int, row_id: int) -> Response:
        """
        Updates the row with the given row_id for the table with the given
        table_id. Also the post data is validated according to the tables field types.

        :param request: The request object
        :param table_id: The id of the table to update the row in
        :param row_id: The id of the row to update
        :return: The updated row values serialized as a json object
        """
        table = TableHandler().get_table(table_id)
        TokenHandler().check_table_permissions(request, "update", table, False)

        user_field_names = "user_field_names" in request.GET
        field_ids, field_names = None, None
        if user_field_names:
            field_names = request.data.keys()
        else:
            field_ids = RowHandler().extract_field_ids_from_dict(request.data)
        model = table.get_model()
        validation_serializer = get_row_serializer_class(
            model,
            field_ids=field_ids,
            field_names_to_include=field_names,
            user_field_names=user_field_names,
        )
        data = validate_data(validation_serializer, request.data)
        try:
            row = action_type_registry.get_by_type(UpdateRowActionType).do(
                request.user,
                table,
                row_id,
                data,
                model=model,
                user_field_names=user_field_names,
            )
        except ValidationError as exc:
            raise RequestBodyValidationException(detail=exc.message) from exc

        serializer_class = get_row_serializer_class(
            model, RowSerializer, is_response=True, user_field_names=user_field_names
        )
        serializer = serializer_class(row)
        return Response(serializer.data)



class CustomerRequestView(RetrieveAPIView):
    permission_classes = []
    authentication_classes = []
    def get(self, request,request_id):
        table = TableHandler().get_table(93)
        user_field_names = "user_field_names" in request.GET
        model = table.get_model()
        try:
            row = table.get_model().objects.get(field_578=request_id)
        except ValidationError as exc:
            raise RequestBodyValidationException(detail=exc.message) from exc

        serializer_class = get_row_serializer_class(
            model, RowSerializer, is_response=True, user_field_names=user_field_names
        )
        serializer = serializer_class(row)
        data=serializer.data
        fields_key = {f'field_{i.id}':i.name for i in Field.objects.filter(table=table)}
        new_data={fields_key.get(k) if k not in ['id','order'] else k:v for k,v in data.items()}
        return Response(new_data)



class OrgFounderMapView(RetrieveAPIView):
    permission_classes = []
    authentication_classes = []
    def get(self, request,request_id):
        table = TableHandler().get_table(54)
        user_field_names = "user_field_names" in request.GET
        model = table.get_model()
        try:
            rows = table.get_model().objects.filter(field_593__field_578=request_id)
        except ValidationError as exc:
            raise RequestBodyValidationException(detail=exc.message) from exc

        serializer_class = get_row_serializer_class(
            model, RowSerializer, is_response=True, user_field_names=user_field_names
        )
        serializer = serializer_class(rows,many=True)
        data=serializer.data
        fields_key = {f'field_{i.id}':i.name for i in Field.objects.filter(table=table)}
        new_data=[]
        for row in data:
            new_data.append({fields_key.get(k) if k not in ['id','order'] else k:v for k,v in row.items()})
        return Response(new_data)



class GetLastId(APIView):
    def get(self,request,table_id,field_id):
        tabel = get_object_or_404(Table, id=table_id)
        get_object_or_404(Field,id=field_id,table=tabel)
        model=tabel.get_model()
        obj=model.objects.aggregate(max_id=Max(f'field_{field_id}'))
        return Response(obj)


class LisTable(ListAPIView):
    permission_classes = []
    serializer_class = TableSerializer
    queryset = Table.objects.filter(database__in=Database.objects.filter(group__in=Group.objects.filter(name=settings.TRIBAL_GROUP_NAME)))


class ListField(ListAPIView):
    serializer_class = FieldSerializer
    queryset = Field.objects.all()
    filter_backends = [DjangoFilterBackend]
    filterset_fields=['table_id']



class TableContent(ListAPIView):

    permission_classes = []

    def get_queryset(self):
        table=get_object_or_404(Table,id=self.kwargs['table_id'])
        model=table.get_model()
        return model.objects.filter(trashed=False)


    def get_serializer_class(self):
        table = get_object_or_404(Table, id=self.kwargs['table_id'])
        model = table.get_model()
        serializer_class = get_row_serializer_class(
            model, RowSerializer, is_response=True, user_field_names=None
        )
        return serializer_class