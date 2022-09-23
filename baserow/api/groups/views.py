from django.db import transaction

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from drf_spectacular.utils import extend_schema
from drf_spectacular.plumbing import build_array_type
from drf_spectacular.openapi import OpenApiParameter, OpenApiTypes

from baserow.api.decorators import validate_body, map_exceptions
from baserow.api.errors import (
    ERROR_USER_NOT_IN_GROUP,
    ERROR_GROUP_DOES_NOT_EXIST,
    ERROR_USER_INVALID_GROUP_PERMISSIONS,
)
from baserow.api.schemas import get_error_schema, CLIENT_SESSION_ID_SCHEMA_PARAMETER
from baserow.api.groups.users.serializers import GroupUserGroupSerializer
from baserow.api.trash.errors import ERROR_CANNOT_DELETE_ALREADY_DELETED_ITEM
from baserow.core.models import GroupUser
from baserow.core.handler import CoreHandler
from baserow.core.exceptions import (
    UserNotInGroup,
    GroupDoesNotExist,
    GroupUserIsLastAdmin,
    UserInvalidGroupPermissionsError,
)
from baserow.core.trash.exceptions import CannotDeleteAlreadyDeletedItem

from .serializers import GroupSerializer, OrderGroupsSerializer
from .schemas import group_user_schema
from .errors import ERROR_GROUP_USER_IS_LAST_ADMIN
from baserow.core.action.registries import action_type_registry
from baserow.core.actions import (
    DeleteGroupActionType,
    CreateGroupActionType,
    UpdateGroupActionType,
    OrderGroupsActionType,
)


class GroupsView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        tags=["Groups"],
        operation_id="list_groups",
        description=(
            "Lists all the groups of the authorized user. A group can contain "
            "multiple applications like a database. Multiple users can have "
            "access to a group. For example each company could have their own group "
            "containing databases related to that company. The order of the groups "
            "are custom for each user. The order is configurable via the "
            "**order_groups** endpoint."
        ),
        responses={200: build_array_type(group_user_schema)},
    )
    def get(self, request):
        """Responds with a list of serialized groups where the user is part of."""

        groups = GroupUser.objects.filter(user=request.user).select_related("group")
        serializer = GroupUserGroupSerializer(groups, many=True)
        return Response(serializer.data)

    @extend_schema(
        parameters=[CLIENT_SESSION_ID_SCHEMA_PARAMETER],
        tags=["Groups"],
        operation_id="create_group",
        description=(
            "Creates a new group where only the authorized user has access to. No "
            "initial data like database applications are added, they have to be "
            "created via other endpoints."
        ),
        request=GroupSerializer,
        responses={200: group_user_schema},
    )
    @transaction.atomic
    @validate_body(GroupSerializer)
    def post(self, request, data):
        """Creates a new group for a user."""

        group_user = action_type_registry.get_by_type(CreateGroupActionType).do(
            request.user, data["name"]
        )
        return Response(GroupUserGroupSerializer(group_user).data)


class GroupView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="group_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="Updates the group related to the provided value.",
            ),
            CLIENT_SESSION_ID_SCHEMA_PARAMETER,
        ],
        tags=["Groups"],
        operation_id="update_group",
        description=(
            "Updates the existing group related to the provided `group_id` parameter "
            "if the authorized user belongs to the group. It is not yet possible to "
            "add additional users to a group."
        ),
        request=GroupSerializer,
        responses={
            200: GroupSerializer,
            400: get_error_schema(
                [
                    "ERROR_USER_NOT_IN_GROUP",
                    "ERROR_REQUEST_BODY_VALIDATION",
                    "ERROR_USER_INVALID_GROUP_PERMISSIONS",
                ]
            ),
            404: get_error_schema(["ERROR_GROUP_DOES_NOT_EXIST"]),
        },
    )
    @transaction.atomic
    @validate_body(GroupSerializer)
    @map_exceptions(
        {
            GroupDoesNotExist: ERROR_GROUP_DOES_NOT_EXIST,
            UserNotInGroup: ERROR_USER_NOT_IN_GROUP,
            UserInvalidGroupPermissionsError: ERROR_USER_INVALID_GROUP_PERMISSIONS,
        }
    )
    def patch(self, request, data, group_id):
        """Updates the group if it belongs to a user."""

        group = CoreHandler().get_group_for_update(group_id)
        action_type_registry.get_by_type(UpdateGroupActionType).do(
            request.user, group, data["name"]
        )
        return Response(GroupSerializer(group).data)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="group_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="Deletes the group related to the provided value.",
            ),
            CLIENT_SESSION_ID_SCHEMA_PARAMETER,
        ],
        tags=["Groups"],
        operation_id="delete_group",
        description=(
            "Deletes an existing group if the authorized user belongs to the group. "
            "All the applications, databases, tables etc that were in the group are "
            "going to be deleted also."
        ),
        request=GroupSerializer,
        responses={
            200: group_user_schema,
            400: get_error_schema(
                [
                    "ERROR_USER_NOT_IN_GROUP",
                    "ERROR_REQUEST_BODY_VALIDATION",
                    "ERROR_USER_INVALID_GROUP_PERMISSIONS",
                    "ERROR_CANNOT_DELETE_ALREADY_DELETED_ITEM",
                ]
            ),
            404: get_error_schema(["ERROR_GROUP_DOES_NOT_EXIST"]),
        },
    )
    @transaction.atomic
    @map_exceptions(
        {
            GroupDoesNotExist: ERROR_GROUP_DOES_NOT_EXIST,
            UserNotInGroup: ERROR_USER_NOT_IN_GROUP,
            UserInvalidGroupPermissionsError: ERROR_USER_INVALID_GROUP_PERMISSIONS,
            CannotDeleteAlreadyDeletedItem: ERROR_CANNOT_DELETE_ALREADY_DELETED_ITEM,
        }
    )
    def delete(self, request, group_id: int):
        """Deletes an existing group if it belongs to a user."""

        locked_group = CoreHandler().get_group_for_update(group_id)
        action_type_registry.get_by_type(DeleteGroupActionType).do(
            request.user, locked_group
        )
        return Response(status=204)


class GroupLeaveView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="group_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="Leaves the group related to the value.",
            )
        ],
        tags=["Groups"],
        operation_id="leave_group",
        description=(
            "Makes the authenticated user leave the group related to the provided "
            "`group_id` if the user is in that group. If the user is the last admin "
            "in the group, he will not be able to leave it. There must always be one "
            "admin in the group, otherwise it will be left without control. If that "
            "is the case, he must either delete the group or give another member admin "
            "permissions first."
        ),
        request=None,
        responses={
            204: None,
            400: get_error_schema(
                ["ERROR_USER_NOT_IN_GROUP", "ERROR_GROUP_USER_IS_LAST_ADMIN"]
            ),
            404: get_error_schema(["ERROR_GROUP_DOES_NOT_EXIST"]),
        },
    )
    @transaction.atomic
    @map_exceptions(
        {
            GroupDoesNotExist: ERROR_GROUP_DOES_NOT_EXIST,
            UserNotInGroup: ERROR_USER_NOT_IN_GROUP,
            GroupUserIsLastAdmin: ERROR_GROUP_USER_IS_LAST_ADMIN,
        }
    )
    def post(self, request, group_id):
        """Leaves the group if the user is a member of it."""

        handler = CoreHandler()
        group = handler.get_group(group_id)
        handler.leave_group(request.user, group)
        return Response(status=204)


class GroupOrderView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        parameters=[CLIENT_SESSION_ID_SCHEMA_PARAMETER],
        tags=["Groups"],
        operation_id="order_groups",
        description=(
            "Changes the order of the provided group ids to the matching position that "
            "the id has in the list. If the authorized user does not belong to the "
            "group it will be ignored. The order will be custom for each user."
        ),
        request=OrderGroupsSerializer,
        responses={
            204: None,
        },
    )
    @validate_body(OrderGroupsSerializer)
    @transaction.atomic
    def post(self, request, data):
        """Updates to order of some groups for a user."""

        action_type_registry.get_by_type(OrderGroupsActionType).do(
            request.user, data["groups"]
        )
        return Response(status=204)
