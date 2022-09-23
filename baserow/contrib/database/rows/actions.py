import dataclasses
from copy import deepcopy

from decimal import Decimal
from typing import Any, Dict, Optional, Type, List

from django.contrib.auth.models import AbstractUser
from baserow.contrib.database.table.handler import TableHandler

from baserow.core.action.models import Action
from baserow.core.action.registries import ActionType, ActionScopeStr
from baserow.contrib.database.action.scopes import TableActionScopeType
from baserow.contrib.database.rows.handler import (
    GeneratedTableModelForUpdate,
    RowHandler,
)
from baserow.contrib.database.table.models import (
    GeneratedTableModel,
    Table,
)
from baserow.core.trash.handler import TrashHandler


class CreateRowActionType(ActionType):
    type = "create_row"

    @dataclasses.dataclass
    class Params:
        table_id: int
        row_id: int

    @classmethod
    def do(
        cls,
        user: AbstractUser,
        table: Table,
        values: Optional[Dict[str, Any]] = None,
        model: Optional[Type[GeneratedTableModel]] = None,
        before_row: Optional[GeneratedTableModel] = None,
        user_field_names: bool = False,
    ) -> GeneratedTableModel:
        """
        Creates a new row for a given table with the provided values if the user
        belongs to the related group. It also calls the row_created signal.
        See the baserow.contrib.database.rows.handler.RowHandler.create_row
        for more information.
        Undoing this action trashes the row and redoing restores it.

        :param user: The user of whose behalf the row is created.
        :param table: The table for which to create a row for.
        :param values: The values that must be set upon creating the row. The keys must
            be the field ids.
        :param model: If a model is already generated it can be provided here to avoid
            having to generate the model again.
        :param before_row: If provided the new row will be placed right before that row
            instance.
        :param user_field_names: Whether or not the values are keyed by the internal
            Baserow field name (field_1,field_2 etc) or by the user field names.
        :return: The created row instance.
        """

        row = RowHandler().create_row(
            user,
            table,
            values=values,
            model=model,
            before_row=before_row,
            user_field_names=user_field_names,
        )

        params = cls.Params(table.id, row.id)
        cls.register_action(user, params, cls.scope(table.id))

        return row

    @classmethod
    def scope(cls, table_id) -> ActionScopeStr:
        return TableActionScopeType.value(table_id)

    @classmethod
    def undo(cls, user: AbstractUser, params: Params, action_being_undone: Action):
        RowHandler().delete_row_by_id(
            user, TableHandler().get_table(params.table_id), params.row_id
        )

    @classmethod
    def redo(cls, user: AbstractUser, params: Params, action_being_redone: Action):
        TrashHandler.restore_item(
            user, "row", params.row_id, parent_trash_item_id=params.table_id
        )


class CreateRowsActionType(ActionType):
    type = "create_rows"

    @dataclasses.dataclass
    class Params:
        table_id: int
        row_ids: List[int]
        trashed_rows_entry_id: Optional[int] = None

    @classmethod
    def do(
        cls,
        user: AbstractUser,
        table: Table,
        rows_values: List[Dict[str, Any]],
        before_row: Optional[GeneratedTableModel] = None,
        model: Optional[Type[GeneratedTableModel]] = None,
    ) -> List[GeneratedTableModel]:
        """
        Creates rows for a given table with the provided values if the user
        belongs to the related group. It also calls the rows_created signal.
        See the baserow.contrib.database.rows.handler.RowHandler.create_rows
        for more information.
        Undoing this action trashes the rows sand redoing restores them all.

        :param user: The user of whose behalf the rows are created.
        :param table: The table for which the rows should be created.
        :param rows_values: List of rows values for rows that need to be created.
        :param before_row: If provided the new rows will be placed right before
            the row with this id.
        :param model: If the correct model has already been generated it can be
            provided so that it does not have to be generated for a second time.
        :return: The created list of rows instances.
        """

        rows = RowHandler().create_rows(
            user, table, rows_values, before_row=before_row, model=model
        )

        params = cls.Params(table.id, [row.id for row in rows])
        cls.register_action(user, params, cls.scope(table.id))

        return rows

    @classmethod
    def scope(cls, table_id) -> ActionScopeStr:
        return TableActionScopeType.value(table_id)

    @classmethod
    def undo(cls, user: AbstractUser, params: Params, action_being_undone: Action):
        trashed_rows_trash_entry = RowHandler().delete_rows(
            user, TableHandler().get_table(params.table_id), params.row_ids
        )
        params.trashed_rows_entry_id = trashed_rows_trash_entry.id
        action_being_undone.params = params

    @classmethod
    def redo(cls, user: AbstractUser, params: Params, action_being_redone: Action):
        TrashHandler.restore_item(
            user,
            "rows",
            params.trashed_rows_entry_id,
            parent_trash_item_id=params.table_id,
        )


class DeleteRowActionType(ActionType):
    type = "delete_row"

    @dataclasses.dataclass
    class Params:
        table_id: int
        row_id: int

    @classmethod
    def do(
        cls,
        user: AbstractUser,
        table: Table,
        row_id: int,
        model: Optional[Type[GeneratedTableModel]] = None,
    ):
        """
        Deletes an existing row of the given table and with row_id.
        See the baserow.contrib.database.rows.handler.RowHandler.delete_row_by_id
        for more information.
        Undoing this action restores the row and redoing trashes it.

        :param user: The user of whose behalf the change is made.
        :param table: The table for which the row must be deleted.
        :param row_id: The id of the row that must be deleted.
        :param model: If the correct model has already been generated, it can be
            provided so that it does not have to be generated for a second time.
        :raises RowDoesNotExist: When the row with the provided id does not exist.
        """

        RowHandler().delete_row_by_id(user, table, row_id, model=model)

        params = cls.Params(table.id, row_id)
        cls.register_action(user, params, cls.scope(table.id))

    @classmethod
    def scope(cls, table_id) -> ActionScopeStr:
        return TableActionScopeType.value(table_id)

    @classmethod
    def undo(cls, user: AbstractUser, params: Params, action_being_undone: Action):
        TrashHandler.restore_item(
            user, "row", params.row_id, parent_trash_item_id=params.table_id
        )

    @classmethod
    def redo(cls, user: AbstractUser, params: Params, action_being_redone: Action):
        RowHandler().delete_row_by_id(
            user, TableHandler().get_table(params.table_id), params.row_id
        )


class DeleteRowsActionType(ActionType):
    type = "delete_rows"

    @dataclasses.dataclass
    class Params:
        table_id: int
        row_ids: List[int]
        trashed_rows_entry_id: int

    @classmethod
    def do(
        cls,
        user: AbstractUser,
        table: Table,
        row_ids: List[int],
        model: Optional[Type[GeneratedTableModel]] = None,
    ):
        """
        Deletes rows of the given table with the given row_ids.
        See the baserow.contrib.database.rows.handler.RowHandler.delete_rows
        for more information.
        Undoing this action restores the original rows and redoing trashes them again.

        :param user: The user of whose behalf the change is made.
        :param table: The table for which the row must be deleted.
        :param row_ids: The id of the row that must be deleted.
        :param model: If the correct model has already been generated, it can be
            provided so that it does not have to be generated for a second time.
        :raises RowDoesNotExist: When the row with the provided id does not exist.
        """

        trashed_rows_entry = RowHandler().delete_rows(user, table, row_ids, model=model)

        params = cls.Params(table.id, row_ids, trashed_rows_entry.id)
        cls.register_action(user, params, cls.scope(table.id))

    @classmethod
    def scope(cls, table_id) -> ActionScopeStr:
        return TableActionScopeType.value(table_id)

    @classmethod
    def undo(cls, user: AbstractUser, params: Params, action_being_undone: Action):
        TrashHandler.restore_item(
            user,
            "rows",
            params.trashed_rows_entry_id,
            parent_trash_item_id=params.table_id,
        )

    @classmethod
    def redo(cls, user: AbstractUser, params: Params, action_being_redone: Action):
        trashed_rows_entry = RowHandler().delete_rows(
            user, TableHandler().get_table(params.table_id), params.row_ids
        )
        params.trashed_rows_entry_id = trashed_rows_entry.id
        action_being_redone.params = params


def get_rows_displacement(
    model: Type[GeneratedTableModel],
    original_row_order: Decimal,
    new_row_order: Decimal,
) -> int:
    """
    Returns the rows count between two row orders.

    :param model: The model of the row.
    :param original_row_order: The row order before move operation.
    :param new_row_order: The row order after move operation.
    """

    def get_displacement(
        lower_order: Decimal,
        higher_order: Decimal,
    ) -> int:
        """Return the rows count between two orders value."""

        return model.objects.filter(
            order__gt=lower_order, order__lt=higher_order
        ).count()

    if new_row_order > original_row_order:
        return get_displacement(original_row_order, new_row_order)
    else:
        return -get_displacement(new_row_order, original_row_order)


def get_before_row_from_displacement(
    row: GeneratedTableModel,
    model: Type[GeneratedTableModel],
    displacement: int,
) -> Optional[GeneratedTableModel]:
    """
    Returns the row instance to use as before in RowHandler().move_row,
    given the displacement.

    :param row: The row instance to use as reference.
    :param model: The model of the row to access data in the table.
    :param displacement: The displacement value.
    """

    if displacement >= 0:
        # a positive displacement means that the row is moved down (bigger order value)
        # so take the row with the order value immediately after the desired position
        try:
            return model.objects.filter(order__gt=row.order).order_by("order")[
                displacement
            ]
        except IndexError:  # after the last line
            return None
    else:
        # displacement < 0 means we are moving the row up (lower order value) but we
        # still need the row with the order value immediately after the desired position
        queryset = model.objects.filter(order__lt=row.order).order_by("-order")
        try:
            # We want to find a row N rows above the provided row, but specifically
            # the before row. The before row is always the row after the slot where
            # we want to move the row. So we minus one from the displacement to get
            # the position instead of this before row.
            return queryset[abs(displacement) - 1]
        except IndexError:
            # cannot be before the first row, so take the first available
            # (the one with the lowest order value as before row).
            return queryset.last()


class MoveRowActionType(ActionType):
    type = "move_row"

    @dataclasses.dataclass
    class Params:
        table_id: int
        row_id: int
        rows_displacement: int

    @classmethod
    def do(
        cls,
        user: AbstractUser,
        table: Table,
        row_id: int,
        before_row: Optional[GeneratedTableModel] = None,
        model: Optional[Type[GeneratedTableModel]] = None,
    ) -> GeneratedTableModelForUpdate:
        """
        Moves the row before another row or to the end if no before row is provided.
        This moving is done by updating the `order` value of the order.
        See the baserow.contrib.database.rows.handler.RowHandler.move_row
        for more information.
        Undoing this action moves the row back however many positions it was moved
        initially.
        Redoing moves the row in the same direction and number of positions it was
        moved initially.

        :param user: The user of whose behalf the row is moved
        :param table: The table that contains the row that needs to be moved.
        :param row_id: The id of the row that needs to be moved.
        :param before_row: If provided the new row will be placed right before that row
            instance. Otherwise the row will be moved to the end.
        :param model: If the correct model has already been generated, it can be
            provided so that it does not have to be generated for a second time.
        """

        if model is None:
            model = table.get_model()

        row_handler = RowHandler()
        row = row_handler.get_row_for_update(user, table, row_id, model=model)

        original_row_order = row.order

        updated_row = row_handler.move_row(
            user, table, row, before_row=before_row, model=model
        )

        rows_displacement = get_rows_displacement(
            model, original_row_order, updated_row.order
        )

        # no need to register the action if the row was not moved
        if rows_displacement == 0:
            return updated_row

        params = cls.Params(table.id, row.id, rows_displacement)
        cls.register_action(user, params, cls.scope(table.id))

        return updated_row

    @classmethod
    def scope(cls, table_id) -> ActionScopeStr:
        return TableActionScopeType.value(table_id)

    @classmethod
    def undo(cls, user: AbstractUser, params: Params, action_being_undone: Action):
        table = TableHandler().get_table(params.table_id)
        model = table.get_model()

        row_handler = RowHandler()
        row = row_handler.get_row_for_update(user, table, params.row_id, model=model)

        before_row = get_before_row_from_displacement(
            row, model, -params.rows_displacement
        )

        row_handler.move_row(user, table, row, before_row=before_row, model=model)

    @classmethod
    def redo(cls, user: AbstractUser, params: Params, action_being_redone: Action):
        table = TableHandler().get_table(params.table_id)
        model = table.get_model()

        row_handler = RowHandler()
        row = row_handler.get_row_for_update(user, table, params.row_id, model=model)

        before_row = get_before_row_from_displacement(
            row, model, params.rows_displacement
        )

        row_handler.move_row(user, table, row, before_row=before_row, model=model)


class UpdateRowActionType(ActionType):
    type = "update_row"

    @dataclasses.dataclass
    class Params:
        table_id: int
        row_id: int
        original_row_values: Dict[str, Any]
        new_row_values: Dict[str, Any]

    @classmethod
    def do(
        cls,
        user: AbstractUser,
        table: Table,
        row_id: int,
        values: Dict[str, Any],
        model: Optional[Type[GeneratedTableModel]] = None,
        user_field_names: bool = False,
    ) -> GeneratedTableModelForUpdate:
        """
        Updates one or more values of the provided row_id.
        See the baserow.contrib.database.rows.handler.RowHandler.update_row
        for more information.
        Undoing this action restores the original values.
        Redoing set the new values again.

        :param user: The user of whose behalf the change is made.
        :param table: The table for which the row must be updated.
        :param row_id: The id of the row that must be updated.
        :param values: The values that must be updated. The keys must be the field ids.
        :param model: If the correct model has already been generated it can be
            provided so that it does not have to be generated for a second time.
        :param user_field_names: Whether or not the values are keyed by the internal
            Baserow field names (field_1,field_2 etc) or by the user field names.
        :raises RowDoesNotExist: When the row with the provided id does not exist.
        :return: The updated row instance.
        """

        if model is None:
            model = table.get_model()

        row_handler = RowHandler()

        if user_field_names:
            values = row_handler.map_user_field_name_dict_to_internal(
                model._field_objects, values
            )

        row = row_handler.get_row_for_update(
            user, table, row_id, enhance_by_fields=True, model=model
        )
        field_keys = list(values.keys())

        original_row_values = row_handler.get_internal_values_for_fields(
            row, field_keys
        )

        updated_row = row_handler.update_row(user, table, row, values, model=model)

        new_row_values = row_handler.get_internal_values_for_fields(row, field_keys)

        params = cls.Params(
            table.id,
            row.id,
            original_row_values,
            new_row_values,
        )
        cls.register_action(user, params, cls.scope(table.id))

        return updated_row

    @classmethod
    def scope(cls, table_id) -> ActionScopeStr:
        return TableActionScopeType.value(table_id)

    @classmethod
    def undo(cls, user: AbstractUser, params: Params, action_being_undone: Action):
        table = TableHandler().get_table(params.table_id)
        RowHandler().update_row_by_id(
            user, table, row_id=params.row_id, values=params.original_row_values
        )

    @classmethod
    def redo(cls, user: AbstractUser, params: Params, action_being_redone: Action):
        table = TableHandler().get_table(params.table_id)
        RowHandler().update_row_by_id(
            user, table, row_id=params.row_id, values=params.new_row_values
        )


class UpdateRowsActionType(ActionType):
    type = "update_rows"

    @dataclasses.dataclass
    class Params:
        table_id: int
        original_rows_values: List
        new_rows: List

    @classmethod
    def do(
        cls,
        user: AbstractUser,
        table: Table,
        rows: List,
        model: Optional[Type[GeneratedTableModel]] = None,
    ) -> List[GeneratedTableModelForUpdate]:
        """
        Updates field values in batch based on provided rows with the new values.
        See the baserow.contrib.database.rows.handler.RowHandler.update_rows
        for more information.
        Undoing this action restores the original values.
        Redoing set the new values again.

        :param user: The user of whose behalf the change is made.
        :param table: The table for which the rows must be updated.
        :param rows: The rows that must be updated.
        :param model: If the correct model has already been generated it can be
            provided so that it does not have to be generated for a second time.
        :return: The updated rows.
        """

        row_handler = RowHandler()

        if model is None:
            model = table.get_model()

        rows_keys_map = {row["id"]: row.keys() for row in rows}

        row_ids = rows_keys_map.keys()
        original_rows = row_handler.get_rows_for_update(model, row_ids)

        original_rows_values = []
        for row in original_rows:
            original_row_values = row_handler.get_internal_values_for_fields(
                row, rows_keys_map[row.id]
            )
            original_row_values["id"] = row.id
            original_rows_values.append(original_row_values)

        new_rows = deepcopy(rows)

        updated_rows = row_handler.update_rows(
            user, table, rows, model=model, rows_to_update=original_rows
        )

        params = cls.Params(table.id, original_rows_values, new_rows)

        cls.register_action(user, params, cls.scope(table.id))

        return updated_rows

    @classmethod
    def scope(cls, table_id) -> ActionScopeStr:
        return TableActionScopeType.value(table_id)

    @classmethod
    def undo(cls, user: AbstractUser, params: Params, action_being_undone: Action):
        table = TableHandler().get_table(params.table_id)
        RowHandler().update_rows(user, table, params.original_rows_values)

    @classmethod
    def redo(cls, user: AbstractUser, params: Params, action_being_redone: Action):
        table = TableHandler().get_table(params.table_id)
        RowHandler().update_rows(user, table, params.new_rows)
