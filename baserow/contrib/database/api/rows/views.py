from typing import Dict, Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from drf_spectacular.openapi import OpenApiParameter, OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from baserow.api.decorators import (
    map_exceptions,
    validate_body,
    validate_query_parameters,
)
from baserow.api.errors import ERROR_USER_NOT_IN_GROUP
from baserow.api.exceptions import (
    RequestBodyValidationException,
    QueryParameterValidationException,
)
from baserow.api.pagination import PageNumberPagination
from baserow.api.schemas import get_error_schema, CLIENT_SESSION_ID_SCHEMA_PARAMETER
from baserow.api.trash.errors import ERROR_CANNOT_DELETE_ALREADY_DELETED_ITEM
from baserow.api.user_files.errors import ERROR_USER_FILE_DOES_NOT_EXIST
from baserow.api.utils import validate_data
from baserow.contrib.database.api.utils import get_include_exclude_fields
from baserow.contrib.database.api.fields.errors import (
    ERROR_ORDER_BY_FIELD_NOT_POSSIBLE,
    ERROR_ORDER_BY_FIELD_NOT_FOUND,
    ERROR_FILTER_FIELD_NOT_FOUND,
    ERROR_FIELD_DOES_NOT_EXIST,
    ERROR_INVALID_SELECT_OPTION_VALUES,
)
from baserow.contrib.database.api.rows.errors import (
    ERROR_ROW_DOES_NOT_EXIST,
    ERROR_ROW_IDS_NOT_UNIQUE,
)
from baserow.contrib.database.api.rows.serializers import (
    example_pagination_row_serializer_class,
)
from baserow.contrib.database.api.tables.errors import ERROR_TABLE_DOES_NOT_EXIST
from baserow.contrib.database.api.tokens.authentications import TokenAuthentication
from baserow.contrib.database.api.tokens.errors import ERROR_NO_PERMISSION_TO_TABLE
from baserow.contrib.database.api.views.errors import (
    ERROR_VIEW_FILTER_TYPE_DOES_NOT_EXIST,
    ERROR_VIEW_FILTER_TYPE_UNSUPPORTED_FIELD,
)
from baserow.contrib.database.fields.exceptions import (
    OrderByFieldNotFound,
    OrderByFieldNotPossible,
    FilterFieldNotFound,
    FieldDoesNotExist,
    AllProvidedMultipleSelectValuesMustBeSelectOption,
)
from baserow.contrib.database.rows.actions import (
    CreateRowActionType,
    CreateRowsActionType,
    DeleteRowActionType,
    DeleteRowsActionType,
    MoveRowActionType,
    UpdateRowActionType,
    UpdateRowsActionType,
)
from baserow.core.action.registries import action_type_registry
from baserow.contrib.database.rows.exceptions import RowDoesNotExist, RowIdsNotUnique
from baserow.contrib.database.rows.handler import RowHandler
from baserow.contrib.database.table.exceptions import TableDoesNotExist
from baserow.contrib.database.table.handler import TableHandler
from baserow.contrib.database.table.models import Table
from baserow.contrib.database.tokens.exceptions import NoPermissionToTable
from baserow.contrib.database.tokens.handler import TokenHandler
from baserow.contrib.database.views.exceptions import (
    ViewFilterTypeNotAllowedForField,
    ViewFilterTypeDoesNotExist,
)
from baserow.contrib.database.views.registries import view_filter_type_registry
from baserow.core.exceptions import UserNotInGroup
from baserow.core.trash.exceptions import CannotDeleteAlreadyDeletedItem
from baserow.core.user_files.exceptions import UserFileDoesNotExist
from .serializers import (
    ListRowsQueryParamsSerializer,
    MoveRowQueryParamsSerializer,
    CreateRowQueryParamsSerializer,
    RowSerializer,
    BatchCreateRowsQueryParamsSerializer,
    BatchDeleteRowsSerializer,
    get_batch_row_serializer_class,
    get_example_row_serializer_class,
    get_row_serializer_class,
    get_example_batch_rows_serializer_class,
)
from baserow.contrib.database.fields.field_filters import (
    FILTER_TYPE_AND,
    FILTER_TYPE_OR,
)
from .schemas import row_names_response_schema


class RowsView(APIView):
    authentication_classes = APIView.authentication_classes + [TokenAuthentication]
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="table_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="Returns the rows of the table related to the provided "
                "value.",
            ),
            OpenApiParameter(
                name="page",
                location=OpenApiParameter.QUERY,
                type=OpenApiTypes.INT,
                description="Defines which page of rows should be returned.",
            ),
            OpenApiParameter(
                name="size",
                location=OpenApiParameter.QUERY,
                type=OpenApiTypes.INT,
                description="Defines how many rows should be returned per page.",
            ),
            OpenApiParameter(
                name="search",
                location=OpenApiParameter.QUERY,
                type=OpenApiTypes.STR,
                description="If provided only rows with data that matches the search "
                "query are going to be returned.",
            ),
            OpenApiParameter(
                name="order_by",
                location=OpenApiParameter.QUERY,
                type=OpenApiTypes.STR,
                description="Optionally the rows can be ordered by provided field ids "
                "separated by comma. By default a field is ordered in ascending (A-Z) "
                "order, but by prepending the field with a '-' it can be ordered "
                "descending (Z-A). "
                "If the `user_field_names` parameter is provided then "
                "instead order_by should be a comma separated list of the actual "
                "field names. For field names with commas you should surround the "
                'name with quotes like so: `order_by=My Field,"Field With , "`. '
                "A backslash can be used to escape field names which contain "
                'double quotes like so: `order_by=My Field,Field with \\"`.',
            ),
            OpenApiParameter(
                name="filter__{field}__{filter}",
                location=OpenApiParameter.QUERY,
                type=OpenApiTypes.STR,
                description=(
                    f"The rows can optionally be filtered by the same view filters "
                    f"available for the views. Multiple filters can be provided if "
                    f"they follow the same format. The field and filter variable "
                    f"indicate how to filter and the value indicates where to filter "
                    f"on.\n\n"
                    f"For example if you provide the following GET parameter "
                    f"`filter__field_1__equal=test` then only rows where the value of "
                    f"field_1 is equal to test are going to be returned.\n\n"
                    f"The following filters are available: "
                    f'{", ".join(view_filter_type_registry.get_types())}.'
                ),
            ),
            OpenApiParameter(
                name="filter_type",
                location=OpenApiParameter.QUERY,
                type=OpenApiTypes.STR,
                description=(
                    "`AND`: Indicates that the rows must match all the provided "
                    "filters.\n"
                    "`OR`: Indicates that the rows only have to match one of the "
                    "filters.\n\n"
                    "This works only if two or more filters are provided."
                ),
            ),
            OpenApiParameter(
                name="include",
                location=OpenApiParameter.QUERY,
                type=OpenApiTypes.STR,
                description=(
                    "All the fields are included in the response by default. You can "
                    "select a subset of fields by providing the include query "
                    "parameter. If you for example provide the following GET "
                    "parameter `include=field_1,field_2` then only the fields with"
                    "id `1` and id `2` are going to be selected and included in the "
                    "response. "
                    "If the `user_field_names` parameter is provided then "
                    "instead include should be a comma separated list of the actual "
                    "field names. For field names with commas you should surround the "
                    'name with quotes like so: `include=My Field,"Field With , "`. '
                    "A backslash can be used to escape field names which contain "
                    'double quotes like so: `include=My Field,Field with \\"`.'
                ),
            ),
            OpenApiParameter(
                name="exclude",
                location=OpenApiParameter.QUERY,
                type=OpenApiTypes.STR,
                description=(
                    "All the fields are included in the response by default. You can "
                    "select a subset of fields by providing the exclude query "
                    "parameter. If you for example provide the following GET "
                    "parameter `exclude=field_1,field_2` then the fields with id `1` "
                    "and id `2` are going to be excluded from the selection and "
                    "response. "
                    "If the `user_field_names` parameter is provided then "
                    "instead exclude should be a comma separated list of the actual "
                    "field names. For field names with commas you should surround the "
                    'name with quotes like so: `exclude=My Field,"Field With , "`. '
                    "A backslash can be used to escape field names which contain "
                    'double quotes like so: `exclude=My Field,Field with \\"`.'
                ),
            ),
            OpenApiParameter(
                name="user_field_names",
                location=OpenApiParameter.QUERY,
                type=OpenApiTypes.BOOL,
                description=(
                    "A flag query parameter which if provided the returned json "
                    "will use the user specified field names instead of internal "
                    "Baserow field names (field_123 etc). "
                ),
            ),
        ],
        tags=["Database table rows"],
        operation_id="list_database_table_rows",
        description=(
            "Lists all the rows of the table related to the provided parameter if the "
            "user has access to the related database's group. The response is "
            "paginated by a page/size style. It is also possible to provide an "
            "optional search query, only rows where the data matches the search query "
            "are going to be returned then. The properties of the returned rows "
            "depends on which fields the table has. For a complete overview of fields "
            "use the **list_database_table_fields** endpoint to list them all. In the "
            "example all field types are listed, but normally the number in "
            "field_{id} key is going to be the id of the field. Or if the GET "
            "parameter `user_field_names` is provided then the keys will be the name "
            "of the field. The value is what the user has provided and the format of "
            "it depends on the fields type."
        ),
        responses={
            200: example_pagination_row_serializer_class,
            400: get_error_schema(
                [
                    "ERROR_USER_NOT_IN_GROUP",
                    "ERROR_REQUEST_BODY_VALIDATION",
                    "ERROR_PAGE_SIZE_LIMIT",
                    "ERROR_INVALID_PAGE",
                    "ERROR_ORDER_BY_FIELD_NOT_FOUND",
                    "ERROR_ORDER_BY_FIELD_NOT_POSSIBLE",
                    "ERROR_FILTER_FIELD_NOT_FOUND",
                    "ERROR_VIEW_FILTER_TYPE_DOES_NOT_EXIST",
                    "ERROR_VIEW_FILTER_TYPE_UNSUPPORTED_FIELD",
                ]
            ),
            401: get_error_schema(["ERROR_NO_PERMISSION_TO_TABLE"]),
            404: get_error_schema(
                ["ERROR_TABLE_DOES_NOT_EXIST", "ERROR_FIELD_DOES_NOT_EXIST"]
            ),
        },
    )
    @map_exceptions(
        {
            UserNotInGroup: ERROR_USER_NOT_IN_GROUP,
            TableDoesNotExist: ERROR_TABLE_DOES_NOT_EXIST,
            NoPermissionToTable: ERROR_NO_PERMISSION_TO_TABLE,
            OrderByFieldNotFound: ERROR_ORDER_BY_FIELD_NOT_FOUND,
            OrderByFieldNotPossible: ERROR_ORDER_BY_FIELD_NOT_POSSIBLE,
            FilterFieldNotFound: ERROR_FILTER_FIELD_NOT_FOUND,
            FieldDoesNotExist: ERROR_FIELD_DOES_NOT_EXIST,
            ViewFilterTypeDoesNotExist: ERROR_VIEW_FILTER_TYPE_DOES_NOT_EXIST,
            ViewFilterTypeNotAllowedForField: ERROR_VIEW_FILTER_TYPE_UNSUPPORTED_FIELD,
        }
    )
    @validate_query_parameters(ListRowsQueryParamsSerializer)
    def get(self, request, table_id, query_params):
        """
        Lists all the rows of the given table id paginated. It is also possible to
        provide a search query.
        """

        table = TableHandler().get_table(table_id)
        table.database.group.has_user(request.user, raise_error=True)

        TokenHandler().check_table_permissions(request, "read", table, False)
        search = query_params.get("search")
        order_by = query_params.get("order_by")
        include = query_params.get("include")
        exclude = query_params.get("exclude")
        user_field_names = query_params.get("user_field_names")
        fields = get_include_exclude_fields(
            table, include, exclude, user_field_names=user_field_names
        )

        model = table.get_model(
            fields=fields,
            field_ids=[] if fields else None,
        )
        queryset = model.objects.all().enhance_by_fields()

        if search:
            queryset = queryset.search_all_fields(search)

        if order_by:
            queryset = queryset.order_by_fields_string(order_by, user_field_names)

        filter_type_query_param = query_params.get("filter_type")
        filter_type = (
            FILTER_TYPE_OR
            if filter_type_query_param.upper() == "OR"
            else FILTER_TYPE_AND
        )
        filter_object = {key: request.GET.getlist(key) for key in request.GET.keys()}
        queryset = queryset.filter_by_fields_object(filter_object, filter_type)

        paginator = PageNumberPagination(limit_page_size=settings.ROW_PAGE_SIZE_LIMIT)
        page = paginator.paginate_queryset(queryset, request, self)
        serializer_class = get_row_serializer_class(
            model, RowSerializer, is_response=True, user_field_names=user_field_names
        )
        serializer = serializer_class(page, many=True)

        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="table_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="Creates a row in the table related to the provided "
                "value.",
            ),
            OpenApiParameter(
                name="before",
                location=OpenApiParameter.QUERY,
                type=OpenApiTypes.INT,
                description="If provided then the newly created row will be "
                "positioned before the row with the provided id.",
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
        operation_id="create_database_table_row",
        description=(
            "Creates a new row in the table if the user has access to the related "
            "table's group. The accepted body fields are depending on the fields "
            "that the table has. For a complete overview of fields use the "
            "**list_database_table_fields** to list them all. None of the fields are "
            "required, if they are not provided the value is going to be `null` or "
            "`false` or some default value is that is set. If you want to add a value "
            "for the field with for example id `10`, the key must be named `field_10`. "
            "Or instead if the `user_field_names` GET param is provided the key must "
            "be the name of the field. Of course multiple fields can be provided in "
            "one request. In the examples below you will find all the different field "
            "types, the numbers/ids in the example are just there for example "
            "purposes, the field_ID must be replaced with the actual id of the field "
            "or the name of the field if `user_field_names` is provided."
        ),
        request=get_example_row_serializer_class(
            example_type="post", user_field_names=True
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
            NoPermissionToTable: ERROR_NO_PERMISSION_TO_TABLE,
            AllProvidedMultipleSelectValuesMustBeSelectOption: ERROR_INVALID_SELECT_OPTION_VALUES,
            UserFileDoesNotExist: ERROR_USER_FILE_DOES_NOT_EXIST,
            RowDoesNotExist: ERROR_ROW_DOES_NOT_EXIST,
        }
    )
    @validate_query_parameters(CreateRowQueryParamsSerializer)
    def post(self, request: Request, table_id: int, query_params) -> Response:
        """
        Creates a new row for the given table_id. Also the post data is validated
        according to the tables field types.
        """

        table = TableHandler().get_table(table_id)

        TokenHandler().check_table_permissions(request, "create", table, False)
        user_field_names = "user_field_names" in request.GET
        model = table.get_model()

        validation_serializer = get_row_serializer_class(
            model, user_field_names=user_field_names
        )
        data = validate_data(validation_serializer, request.data)

        before_id = query_params.get("before")
        before_row = (
            RowHandler().get_row(request.user, table, before_id, model)
            if before_id
            else None
        )

        try:
            row = action_type_registry.get_by_type(CreateRowActionType).do(
                request.user,
                table,
                data,
                model=model,
                before_row=before_row,
                user_field_names=user_field_names,
            )
        except ValidationError as e:
            raise RequestBodyValidationException(detail=e.message)

        serializer_class = get_row_serializer_class(
            model, RowSerializer, is_response=True, user_field_names=user_field_names
        )
        serializer = serializer_class(row)

        return Response(serializer.data)


class RowNamesView(APIView):
    authentication_classes = APIView.authentication_classes + [TokenAuthentication]
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="table__{id}",
                location=OpenApiParameter.QUERY,
                type=OpenApiTypes.STR,
                description=(
                    "A list of comma separated row ids to query from the table with "
                    "id {id}. For example, if you "
                    "want the name of row `42` and `43` from table `28` this parameter "
                    "will be `table__28=42,43`. You can specify multiple rows for "
                    "different tables but every tables must be in the same database. "
                    "You need at least read permission on all specified tables."
                ),
            ),
        ],
        tags=["Database table rows"],
        operation_id="list_database_table_row_names",
        description=(
            "Returns the names of the given row of the given tables. The name"
            "of a row is the primary field value for this row. The result can be used"
            "for example, when you want to display the name of a linked row from "
            "another table."
        ),
        responses={
            200: row_names_response_schema,
            400: get_error_schema(
                [
                    "ERROR_USER_NOT_IN_GROUP",
                ]
            ),
            401: get_error_schema(["ERROR_NO_PERMISSION_TO_TABLE"]),
            404: get_error_schema(["ERROR_TABLE_DOES_NOT_EXIST"]),
        },
    )
    @map_exceptions(
        {
            UserNotInGroup: ERROR_USER_NOT_IN_GROUP,
            TableDoesNotExist: ERROR_TABLE_DOES_NOT_EXIST,
            NoPermissionToTable: ERROR_NO_PERMISSION_TO_TABLE,
        }
    )
    def get(self, request):
        """
        Returns the names (i.e. primary field value) of specified rows of given tables.
        Can be used when you want to display a row name referenced from another table.
        """

        result = {}
        database = None
        table_handler = TableHandler()
        token_handler = TokenHandler()
        row_handler = RowHandler()

        for name, value in request.GET.items():
            if not name.startswith("table__"):
                raise QueryParameterValidationException(
                    detail='Only table Id prefixed by "table__" are allowed as parameter.',
                    code="invalid_parameter",
                )

            try:
                table_id = int(name[7:])
            except ValueError:
                raise QueryParameterValidationException(
                    detail=(f'Failed to parse table id in "{name}".'),
                    code="invalid_table_id",
                )

            try:
                row_ids = [int(id) for id in value.split(",")]
            except ValueError:
                raise QueryParameterValidationException(
                    detail=(
                        f'Failed to parse row ids in "{value}" for '
                        f'"table__{table_id}" parameter.'
                    ),
                    code="invalid_row_ids",
                )

            table_queryset = None
            if database:
                # Once we have the database, we want only tables from the same database
                table_queryset = Table.objects.filter(database=database)

            table = table_handler.get_table(table_id, base_queryset=table_queryset)

            if not database:
                # Check permission once
                database = table.database
                database.group.has_user(request.user, raise_error=True)

            token_handler.check_table_permissions(request, "read", table, False)

            result[table_id] = row_handler.get_row_names(table, row_ids)

        return Response(result)


class RowView(APIView):
    authentication_classes = APIView.authentication_classes + [TokenAuthentication]
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="table_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="Returns the row of the table related to the provided "
                "value.",
            ),
            OpenApiParameter(
                name="row_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="Returns the row related the provided value.",
            ),
            OpenApiParameter(
                name="user_field_names",
                location=OpenApiParameter.QUERY,
                type=OpenApiTypes.BOOL,
                description=(
                    "A flag query parameter which if provided the returned json "
                    "will use the user specified field names instead of internal "
                    "Baserow field names (field_123 etc). "
                ),
            ),
        ],
        tags=["Database table rows"],
        operation_id="get_database_table_row",
        description=(
            "Fetches an existing row from the table if the user has access to the "
            "related table's group. The properties of the returned row depend on "
            "which fields the table has. For a complete overview of fields use the "
            "**list_database_table_fields** endpoint to list them all. In the example "
            "all field types are listed, but normally the number in field_{id} key is "
            "going to be the id of the field of the field. Or if the GET parameter "
            "`user_field_names` is provided then the keys will be the name of the "
            "field. The value is what the user has provided and the format of it "
            "depends on the fields type."
        ),
        responses={
            200: get_example_row_serializer_class(
                example_type="get", user_field_names=True
            ),
            400: get_error_schema(
                ["ERROR_USER_NOT_IN_GROUP", "ERROR_REQUEST_BODY_VALIDATION"]
            ),
            401: get_error_schema(["ERROR_NO_PERMISSION_TO_TABLE"]),
            404: get_error_schema(
                ["ERROR_TABLE_DOES_NOT_EXIST", "ERROR_ROW_DOES_NOT_EXIST"]
            ),
        },
    )
    @map_exceptions(
        {
            UserNotInGroup: ERROR_USER_NOT_IN_GROUP,
            TableDoesNotExist: ERROR_TABLE_DOES_NOT_EXIST,
            RowDoesNotExist: ERROR_ROW_DOES_NOT_EXIST,
            NoPermissionToTable: ERROR_NO_PERMISSION_TO_TABLE,
        }
    )
    def get(self, request, table_id, row_id):
        """
        Responds with a serializer version of the row related to the provided row_id
        and table_id.
        """

        table = TableHandler().get_table(table_id)

        TokenHandler().check_table_permissions(request, "read", table, False)
        user_field_names = "user_field_names" in request.GET
        model = table.get_model()
        row = RowHandler().get_row(request.user, table, row_id, model)
        serializer_class = get_row_serializer_class(
            model, RowSerializer, is_response=True, user_field_names=user_field_names
        )
        serializer = serializer_class(row)

        return Response(serializer.data)

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
        }
    )
    def patch(self, request: Request, table_id: int, row_id: int) -> Response:
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

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="table_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="Deletes the row in the table related to the value.",
            ),
            OpenApiParameter(
                name="row_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="Deletes the row related to the value.",
            ),
            CLIENT_SESSION_ID_SCHEMA_PARAMETER,
        ],
        tags=["Database table rows"],
        operation_id="delete_database_table_row",
        description=(
            "Deletes an existing row in the table if the user has access to the "
            "table's group."
        ),
        responses={
            204: None,
            400: get_error_schema(
                ["ERROR_USER_NOT_IN_GROUP", "ERROR_CANNOT_DELETE_ALREADY_DELETED_ITEM"]
            ),
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
            NoPermissionToTable: ERROR_NO_PERMISSION_TO_TABLE,
            CannotDeleteAlreadyDeletedItem: ERROR_CANNOT_DELETE_ALREADY_DELETED_ITEM,
        }
    )
    def delete(self, request, table_id, row_id):
        """
        Deletes an existing row with the given row_id for table with the given
        table_id.
        """

        table = TableHandler().get_table(table_id)
        TokenHandler().check_table_permissions(request, "delete", table, False)

        action_type_registry.get_by_type(DeleteRowActionType).do(
            request.user, table, row_id
        )

        return Response(status=204)


class RowMoveView(APIView):
    authentication_classes = APIView.authentication_classes + [TokenAuthentication]
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="table_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="Moves the row in the table related to the value.",
            ),
            OpenApiParameter(
                name="row_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="Moves the row related to the value.",
            ),
            OpenApiParameter(
                name="before_id",
                location=OpenApiParameter.QUERY,
                type=OpenApiTypes.INT,
                description="Moves the row related to the given `row_id` before the "
                "row related to the provided value. If not provided, "
                "then the row will be moved to the end.",
            ),
            OpenApiParameter(
                name="user_field_names",
                location=OpenApiParameter.QUERY,
                type=OpenApiTypes.BOOL,
                description=(
                    "A flag query parameter which if provided the returned json "
                    "will use the user specified field names instead of internal "
                    "Baserow field names (field_123 etc). "
                ),
            ),
            CLIENT_SESSION_ID_SCHEMA_PARAMETER,
        ],
        tags=["Database table rows"],
        operation_id="move_database_table_row",
        description="Moves the row related to given `row_id` parameter to another "
        "position. It is only possible to move the row before another existing row or "
        "to the end. If the `before_id` is provided then the row related to "
        "the `row_id` parameter is moved before that row. If the `before_id` "
        "parameter is not provided, then the row will be moved to the end.",
        request=None,
        responses={
            200: get_example_row_serializer_class(
                example_type="get", user_field_names=True
            ),
            400: get_error_schema(["ERROR_USER_NOT_IN_GROUP"]),
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
            NoPermissionToTable: ERROR_NO_PERMISSION_TO_TABLE,
        }
    )
    @validate_query_parameters(MoveRowQueryParamsSerializer)
    def patch(self, request, table_id, row_id, query_params):
        """Moves the row to another position."""

        table = TableHandler().get_table(table_id)

        TokenHandler().check_table_permissions(request, "update", table, False)

        user_field_names = "user_field_names" in request.GET

        model = table.get_model()

        row_handler = RowHandler()

        before_id = query_params.get("before_id")
        before_row = (
            row_handler.get_row(request.user, table, before_id, model=model)
            if before_id
            else None
        )

        row = action_type_registry.get_by_type(MoveRowActionType).do(
            request.user, table, row_id, before_row=before_row, model=model
        )

        serializer_class = get_row_serializer_class(
            model, RowSerializer, is_response=True, user_field_names=user_field_names
        )
        serializer = serializer_class(row)
        return Response(serializer.data)


class BatchRowsView(APIView):
    authentication_classes = APIView.authentication_classes + [TokenAuthentication]
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="table_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="Creates the rows in the table.",
            ),
            OpenApiParameter(
                name="before",
                location=OpenApiParameter.QUERY,
                type=OpenApiTypes.INT,
                description="If provided then the newly created rows will be "
                "positioned before the row with the provided id.",
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
        operation_id="batch_create_database_table_rows",
        description=(
            "Creates new rows in the table if the user has access to the related "
            "table's group. The accepted body fields are depending on the fields "
            "that the table has. For a complete overview of fields use the "
            "**list_database_table_fields** to list them all. None of the fields are "
            "required, if they are not provided the value is going to be `null` or "
            "`false` or some default value is that is set. If you want to add a value "
            "for the field with for example id `10`, the key must be named `field_10`. "
            "Or instead if the `user_field_names` GET param is provided the key must "
            "be the name of the field. Of course multiple fields can be provided in "
            "one request. In the examples below you will find all the different field "
            "types, the numbers/ids in the example are just there for example "
            "purposes, the field_ID must be replaced with the actual id of the field "
            "or the name of the field if `user_field_names` is provided."
            "\n\n **WARNING:** This endpoint doesn't yet work with row created webhooks."
        ),
        request=get_example_batch_rows_serializer_class(
            example_type="post", user_field_names=True
        ),
        responses={
            200: get_example_batch_rows_serializer_class(
                example_type="get", user_field_names=True
            ),
            400: get_error_schema(
                [
                    "ERROR_USER_NOT_IN_GROUP",
                    "ERROR_REQUEST_BODY_VALIDATION",
                    "ERROR_ROW_IDS_NOT_UNIQUE",
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
            RowIdsNotUnique: ERROR_ROW_IDS_NOT_UNIQUE,
            AllProvidedMultipleSelectValuesMustBeSelectOption: ERROR_INVALID_SELECT_OPTION_VALUES,
            NoPermissionToTable: ERROR_NO_PERMISSION_TO_TABLE,
            UserFileDoesNotExist: ERROR_USER_FILE_DOES_NOT_EXIST,
        }
    )
    @validate_query_parameters(BatchCreateRowsQueryParamsSerializer)
    def post(self, request: Request, table_id: int, query_params) -> Response:
        """
        Creates new rows for the given table_id. Also the post data is validated
        according to the tables field types.
        """

        table = TableHandler().get_table(table_id)
        TokenHandler().check_table_permissions(request, "create", table, False)
        model = table.get_model()

        user_field_names = "user_field_names" in request.GET
        before_id = query_params.get("before")
        before_row = (
            RowHandler().get_row(request.user, table, before_id, model)
            if before_id
            else None
        )

        row_validation_serializer = get_row_serializer_class(
            model, user_field_names=user_field_names
        )
        validation_serializer = get_batch_row_serializer_class(
            row_validation_serializer
        )
        data = validate_data(
            validation_serializer, request.data, partial=True, return_validated=True
        )

        try:
            rows = action_type_registry.get_by_type(CreateRowsActionType).do(
                request.user, table, data["items"], before_row, model
            )
        except ValidationError as exc:
            raise RequestBodyValidationException(detail=exc.message)

        response_row_serializer_class = get_row_serializer_class(
            model, RowSerializer, is_response=True, user_field_names=user_field_names
        )
        response_serializer_class = get_batch_row_serializer_class(
            response_row_serializer_class
        )
        response_serializer = response_serializer_class({"items": rows})
        return Response(response_serializer.data)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="table_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="Updates the rows in the table.",
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
        operation_id="batch_update_database_table_rows",
        description=(
            "Updates existing rows in the table if the user has access to the "
            "related table's group. The accepted body fields are depending on the "
            "fields that the table has. For a complete overview of fields use the "
            "**list_database_table_fields** endpoint to list them all. None of the "
            "fields are required, if they are not provided the value is not going to "
            "be updated. "
            "When you want to update a value for the field with id `10`, the key must "
            "be named `field_10`. Or if the GET parameter `user_field_names` is "
            "provided the key of the field to update must be the name of the field. "
            "Multiple different fields to update can be provided for each row. In "
            "the examples below you will find all the different field types, the "
            "numbers/ids in the example are just there for example purposes, "
            "the field_ID must be replaced with the actual id of the field or the name "
            "of the field if `user_field_names` is provided."
            "\n\n **WARNING:** This endpoint doesn't yet work with row updated webhooks."
        ),
        request=get_example_batch_rows_serializer_class(
            example_type="patch_batch", user_field_names=True
        ),
        responses={
            200: get_example_batch_rows_serializer_class(
                example_type="get", user_field_names=True
            ),
            400: get_error_schema(
                [
                    "ERROR_USER_NOT_IN_GROUP",
                    "ERROR_REQUEST_BODY_VALIDATION",
                    "ERROR_ROW_IDS_NOT_UNIQUE",
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
            RowIdsNotUnique: ERROR_ROW_IDS_NOT_UNIQUE,
            AllProvidedMultipleSelectValuesMustBeSelectOption: ERROR_INVALID_SELECT_OPTION_VALUES,
            NoPermissionToTable: ERROR_NO_PERMISSION_TO_TABLE,
            UserFileDoesNotExist: ERROR_USER_FILE_DOES_NOT_EXIST,
        }
    )
    def patch(self, request, table_id):
        """
        Updates all provided rows at once for the table with
        the given table_id.
        """

        table = TableHandler().get_table(table_id)
        TokenHandler().check_table_permissions(request, "update", table, False)
        model = table.get_model()

        user_field_names = "user_field_names" in request.GET

        row_validation_serializer = get_row_serializer_class(
            model,
            user_field_names=user_field_names,
            include_id=True,
            required_fields=["id"],
        )
        validation_serializer = get_batch_row_serializer_class(
            row_validation_serializer
        )
        data = validate_data(
            validation_serializer, request.data, partial=True, return_validated=True
        )

        try:
            rows = action_type_registry.get_by_type(UpdateRowsActionType).do(
                request.user, table, data["items"], model
            )
        except ValidationError as e:
            raise RequestBodyValidationException(detail=e.message)

        response_row_serializer_class = get_row_serializer_class(
            model, RowSerializer, is_response=True, user_field_names=user_field_names
        )
        response_serializer_class = get_batch_row_serializer_class(
            response_row_serializer_class
        )
        response_serializer = response_serializer_class({"items": rows})
        return Response(response_serializer.data)


class BatchDeleteRowsView(APIView):
    authentication_classes = APIView.authentication_classes + [TokenAuthentication]
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="table_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="Deletes the rows in the table related to the value.",
            ),
            CLIENT_SESSION_ID_SCHEMA_PARAMETER,
        ],
        tags=["Database table rows"],
        operation_id="batch_delete_database_table_rows",
        description=(
            "Deletes existing rows in the table if the user has access to the "
            "table's group."
            "\n\n **WARNING:**  This endpoint doesn't yet work with row deleted webhooks."
        ),
        request=BatchDeleteRowsSerializer,
        responses={
            204: None,
            400: get_error_schema(
                [
                    "ERROR_USER_NOT_IN_GROUP",
                    "ERROR_CANNOT_DELETE_ALREADY_DELETED_ITEM",
                    "ERROR_ROW_IDS_NOT_UNIQUE",
                ]
            ),
            404: get_error_schema(
                ["ERROR_TABLE_DOES_NOT_EXIST", "ERROR_ROW_DOES_NOT_EXIST"]
            ),
        },
    )
    @transaction.atomic
    @validate_body(BatchDeleteRowsSerializer)
    @map_exceptions(
        {
            UserNotInGroup: ERROR_USER_NOT_IN_GROUP,
            TableDoesNotExist: ERROR_TABLE_DOES_NOT_EXIST,
            RowDoesNotExist: ERROR_ROW_DOES_NOT_EXIST,
            RowIdsNotUnique: ERROR_ROW_IDS_NOT_UNIQUE,
            NoPermissionToTable: ERROR_NO_PERMISSION_TO_TABLE,
            CannotDeleteAlreadyDeletedItem: ERROR_CANNOT_DELETE_ALREADY_DELETED_ITEM,
        }
    )
    def post(self, request: Request, table_id: int, data: Dict[str, Any]) -> Response:
        """
        Batch deletes existing rows based on provided row ids for the table with
        the given table_id.
        """

        table = TableHandler().get_table(table_id)
        TokenHandler().check_table_permissions(request, "delete", table, False)

        action_type_registry.get_by_type(DeleteRowsActionType).do(
            request.user,
            table,
            row_ids=data["items"],
        )

        return Response(status=204)
