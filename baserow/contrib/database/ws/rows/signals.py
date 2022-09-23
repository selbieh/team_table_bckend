from typing import Dict, Any, Optional, List

from django.db import transaction
from django.dispatch import receiver

from baserow.contrib.database.api.rows.serializers import (
    get_row_serializer_class,
    RowSerializer,
)
from baserow.contrib.database.rows import signals as row_signals
from baserow.contrib.database.rows.registries import row_metadata_registry
from baserow.contrib.database.table.models import GeneratedTableModel
from baserow.ws.registries import page_registry


@receiver(row_signals.row_created)
def row_created(sender, row, before, user, table, model, **kwargs):
    table_page_type = page_registry.get("table")
    transaction.on_commit(
        lambda: table_page_type.broadcast(
            RealtimeRowMessages.row_created(
                table_id=table.id,
                serialized_row=get_row_serializer_class(
                    model, RowSerializer, is_response=True
                )(row).data,
                metadata=row_metadata_registry.generate_and_merge_metadata_for_row(
                    table, row.id
                ),
                before=before,
            ),
            getattr(user, "web_socket_id", None),
            table_id=table.id,
        )
    )


@receiver(row_signals.rows_created)
def rows_created(sender, rows, before, user, table, model, **kwargs):
    table_page_type = page_registry.get("table")
    transaction.on_commit(
        lambda: table_page_type.broadcast(
            RealtimeRowMessages.rows_created(
                table_id=table.id,
                serialized_rows=get_row_serializer_class(
                    model, RowSerializer, is_response=True
                )(rows, many=True).data,
                metadata=row_metadata_registry.generate_and_merge_metadata_for_rows(
                    table, [row.id for row in rows]
                ),
                before=before,
            ),
            getattr(user, "web_socket_id", None),
            table_id=table.id,
        )
    )


@receiver(row_signals.before_row_update)
def before_row_update(sender, row, user, table, model, updated_field_ids, **kwargs):
    # Generate a serialized version of the row before it is updated. The
    # `row_updated` receiver needs this serialized version because it can't serialize
    # the old row after it has been updated.
    return get_row_serializer_class(model, RowSerializer, is_response=True)(row).data


@receiver(row_signals.before_rows_update)
def before_rows_update(sender, rows, user, table, model, updated_field_ids, **kwargs):
    return get_row_serializer_class(model, RowSerializer, is_response=True)(
        rows, many=True
    ).data


@receiver(row_signals.row_updated)
def row_updated(
    sender, row, user, table, model, before_return, updated_field_ids, **kwargs
):
    table_page_type = page_registry.get("table")
    transaction.on_commit(
        lambda: table_page_type.broadcast(
            RealtimeRowMessages.row_updated(
                table_id=table.id,
                serialized_row_before_update=dict(before_return)[before_row_update],
                serialized_row=get_row_serializer_class(
                    model, RowSerializer, is_response=True
                )(row).data,
                metadata=row_metadata_registry.generate_and_merge_metadata_for_row(
                    table, row.id
                ),
            ),
            getattr(user, "web_socket_id", None),
            table_id=table.id,
        )
    )


@receiver(row_signals.rows_updated)
def rows_updated(
    sender, rows, user, table, model, before_return, updated_field_ids, **kwargs
):
    table_page_type = page_registry.get("table")
    transaction.on_commit(
        lambda: table_page_type.broadcast(
            RealtimeRowMessages.rows_updated(
                table_id=table.id,
                serialized_rows_before_update=dict(before_return)[before_rows_update],
                serialized_rows=get_row_serializer_class(
                    model, RowSerializer, is_response=True
                )(rows, many=True).data,
                metadata=row_metadata_registry.generate_and_merge_metadata_for_rows(
                    table, [row.id for row in rows]
                ),
            ),
            getattr(user, "web_socket_id", None),
            table_id=table.id,
        )
    )


@receiver(row_signals.before_row_delete)
def before_row_delete(sender, row, user, table, model, **kwargs):
    # Generate a serialized version of the row before it is deleted. The
    # `row_deleted` receiver needs this serialized version because it can't serialize
    # the row after is has been deleted.
    return get_row_serializer_class(model, RowSerializer, is_response=True)(row).data


@receiver(row_signals.before_rows_delete)
def before_rows_delete(sender, rows, user, table, model, **kwargs):
    return get_row_serializer_class(model, RowSerializer, is_response=True)(
        rows, many=True
    ).data


@receiver(row_signals.row_deleted)
def row_deleted(sender, row_id, row, user, table, model, before_return, **kwargs):
    table_page_type = page_registry.get("table")
    transaction.on_commit(
        lambda: table_page_type.broadcast(
            RealtimeRowMessages.row_deleted(
                table_id=table.id, serialized_row=dict(before_return)[before_row_delete]
            ),
            getattr(user, "web_socket_id", None),
            table_id=table.id,
        )
    )


@receiver(row_signals.rows_deleted)
def rows_deleted(sender, rows, user, table, model, before_return, **kwargs):
    table_page_type = page_registry.get("table")
    transaction.on_commit(
        lambda: table_page_type.broadcast(
            RealtimeRowMessages.rows_deleted(
                table_id=table.id,
                serialized_rows=dict(before_return)[before_rows_delete],
            ),
            getattr(user, "web_socket_id", None),
            table_id=table.id,
        )
    )


class RealtimeRowMessages:
    """
    A collection of functions which construct the payloads for the realtime
    websocket messages related to rows.
    """

    @staticmethod
    def row_deleted(table_id: int, serialized_row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": "row_deleted",
            "table_id": table_id,
            "row_id": serialized_row["id"],
            # The web-frontend expects a serialized version of the row that is
            # deleted in order the estimate what position the row had in the view,
            # or find which kanban column the row was in etc.
            "row": serialized_row,
        }

    @staticmethod
    def rows_deleted(
        table_id: int, serialized_rows: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        return {
            "type": "rows_deleted",
            "table_id": table_id,
            "row_ids": [r["id"] for r in serialized_rows],
            "rows": serialized_rows,
        }

    @staticmethod
    def row_created(
        table_id: int,
        serialized_row: Dict[str, Any],
        metadata: Dict[str, Any],
        before: Optional[GeneratedTableModel],
    ) -> Dict[str, Any]:
        return {
            "type": "row_created",
            "table_id": table_id,
            "row": serialized_row,
            "metadata": metadata,
            "before_row_id": before.id if before else None,
        }

    @staticmethod
    def rows_created(
        table_id: int,
        serialized_rows: List[Dict[str, Any]],
        metadata: Dict[str, Any],
        before: Optional[GeneratedTableModel],
    ) -> Dict[str, Any]:
        return {
            "type": "rows_created",
            "table_id": table_id,
            "rows": serialized_rows,
            "metadata": metadata,
            "before_row_id": before.id if before else None,
        }

    @staticmethod
    def row_updated(
        table_id: int,
        serialized_row_before_update: Dict[str, Any],
        serialized_row: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "type": "row_updated",
            "table_id": table_id,
            # The web-frontend expects a serialized version of the row before it
            # was updated in order the estimate what position the row had in the
            # view.
            "row_before_update": serialized_row_before_update,
            "row": serialized_row,
            "metadata": metadata,
        }

    @staticmethod
    def rows_updated(
        table_id: int,
        serialized_rows_before_update: List[Dict[str, Any]],
        serialized_rows: List[Dict[str, Any]],
        metadata: Dict[int, Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "type": "rows_updated",
            "table_id": table_id,
            # The web-frontend expects a serialized version of the rows before it
            # was updated in order to estimate what position the row had in the
            # view.
            "rows_before_update": serialized_rows_before_update,
            "rows": serialized_rows,
            "metadata": metadata,
        }
