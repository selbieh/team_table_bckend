from django.dispatch import receiver
from django.db import transaction

from baserow.ws.registries import page_registry

from baserow.contrib.database.views import signals as view_signals
from baserow.contrib.database.views.registries import view_type_registry
from baserow.contrib.database.api.views.serializers import (
    ViewSerializer,
    ViewFilterSerializer,
    ViewSortSerializer,
    ViewDecorationSerializer,
)


@receiver(view_signals.view_created)
def view_created(sender, view, user, **kwargs):
    table_page_type = page_registry.get("table")
    transaction.on_commit(
        lambda: table_page_type.broadcast(
            {
                "type": "view_created",
                "view": view_type_registry.get_serializer(
                    view,
                    ViewSerializer,
                    filters=True,
                    sortings=True,
                    decorations=True,
                ).data,
            },
            getattr(user, "web_socket_id", None),
            table_id=view.table_id,
        )
    )


@receiver(view_signals.view_updated)
def view_updated(sender, view, user, **kwargs):
    table_page_type = page_registry.get("table")
    transaction.on_commit(
        lambda: table_page_type.broadcast(
            {
                "type": "view_updated",
                "view_id": view.id,
                "view": view_type_registry.get_serializer(
                    view,
                    ViewSerializer,
                    # We do not want to broad cast the filters, decorations and sortings
                    # every time the view changes.
                    # There are separate views and handlers for them
                    # each will broad cast their own message.
                    filters=False,
                    sortings=False,
                    decorations=False,
                ).data,
            },
            getattr(user, "web_socket_id", None),
            table_id=view.table_id,
        )
    )


@receiver(view_signals.view_deleted)
def view_deleted(sender, view_id, view, user, **kwargs):
    table_page_type = page_registry.get("table")
    transaction.on_commit(
        lambda: table_page_type.broadcast(
            {"type": "view_deleted", "table_id": view.table_id, "view_id": view_id},
            getattr(user, "web_socket_id", None),
            table_id=view.table_id,
        )
    )


@receiver(view_signals.views_reordered)
def views_reordered(sender, table, order, user, **kwargs):
    table_page_type = page_registry.get("table")
    transaction.on_commit(
        lambda: table_page_type.broadcast(
            {"type": "views_reordered", "table_id": table.id, "order": order},
            getattr(user, "web_socket_id", None),
            table_id=table.id,
        )
    )


@receiver(view_signals.view_filter_created)
def view_filter_created(sender, view_filter, user, **kwargs):
    table_page_type = page_registry.get("table")
    transaction.on_commit(
        lambda: table_page_type.broadcast(
            {
                "type": "view_filter_created",
                "view_filter": ViewFilterSerializer(view_filter).data,
            },
            getattr(user, "web_socket_id", None),
            table_id=view_filter.view.table_id,
        )
    )


@receiver(view_signals.view_filter_updated)
def view_filter_updated(sender, view_filter, user, **kwargs):
    table_page_type = page_registry.get("table")
    transaction.on_commit(
        lambda: table_page_type.broadcast(
            {
                "type": "view_filter_updated",
                "view_filter_id": view_filter.id,
                "view_filter": ViewFilterSerializer(view_filter).data,
            },
            getattr(user, "web_socket_id", None),
            table_id=view_filter.view.table_id,
        )
    )


@receiver(view_signals.view_filter_deleted)
def view_filter_deleted(sender, view_filter_id, view_filter, user, **kwargs):
    table_page_type = page_registry.get("table")
    transaction.on_commit(
        lambda: table_page_type.broadcast(
            {
                "type": "view_filter_deleted",
                "view_id": view_filter.view_id,
                "view_filter_id": view_filter_id,
            },
            getattr(user, "web_socket_id", None),
            table_id=view_filter.view.table_id,
        )
    )


@receiver(view_signals.view_sort_created)
def view_sort_created(sender, view_sort, user, **kwargs):
    table_page_type = page_registry.get("table")
    transaction.on_commit(
        lambda: table_page_type.broadcast(
            {
                "type": "view_sort_created",
                "view_sort": ViewSortSerializer(view_sort).data,
            },
            getattr(user, "web_socket_id", None),
            table_id=view_sort.view.table_id,
        )
    )


@receiver(view_signals.view_sort_updated)
def view_sort_updated(sender, view_sort, user, **kwargs):
    table_page_type = page_registry.get("table")
    transaction.on_commit(
        lambda: table_page_type.broadcast(
            {
                "type": "view_sort_updated",
                "view_sort_id": view_sort.id,
                "view_sort": ViewSortSerializer(view_sort).data,
            },
            getattr(user, "web_socket_id", None),
            table_id=view_sort.view.table_id,
        )
    )


@receiver(view_signals.view_sort_deleted)
def view_sort_deleted(sender, view_sort_id, view_sort, user, **kwargs):
    table_page_type = page_registry.get("table")
    transaction.on_commit(
        lambda: table_page_type.broadcast(
            {
                "type": "view_sort_deleted",
                "view_id": view_sort.view_id,
                "view_sort_id": view_sort_id,
            },
            getattr(user, "web_socket_id", None),
            table_id=view_sort.view.table_id,
        )
    )


@receiver(view_signals.view_decoration_created)
def view_decoration_created(sender, view_decoration, user, **kwargs):
    table_page_type = page_registry.get("table")
    transaction.on_commit(
        lambda: table_page_type.broadcast(
            {
                "type": "view_decoration_created",
                "view_decoration": ViewDecorationSerializer(view_decoration).data,
            },
            getattr(user, "web_socket_id", None),
            table_id=view_decoration.view.table_id,
        )
    )


@receiver(view_signals.view_decoration_updated)
def view_decoration_updated(sender, view_decoration, user, **kwargs):
    table_page_type = page_registry.get("table")
    transaction.on_commit(
        lambda: table_page_type.broadcast(
            {
                "type": "view_decoration_updated",
                "view_decoration_id": view_decoration.id,
                "view_decoration": ViewDecorationSerializer(view_decoration).data,
            },
            getattr(user, "web_socket_id", None),
            table_id=view_decoration.view.table_id,
        )
    )


@receiver(view_signals.view_decoration_deleted)
def view_decoration_deleted(
    sender, view_decoration_id, view_decoration, user, **kwargs
):
    table_page_type = page_registry.get("table")
    transaction.on_commit(
        lambda: table_page_type.broadcast(
            {
                "type": "view_decoration_deleted",
                "view_id": view_decoration.view_id,
                "view_decoration_id": view_decoration_id,
            },
            getattr(user, "web_socket_id", None),
            table_id=view_decoration.view.table_id,
        )
    )


@receiver(view_signals.view_field_options_updated)
def view_field_options_updated(sender, view, user, **kwargs):
    table_page_type = page_registry.get("table")
    view_type = view_type_registry.get_by_model(view.specific_class)
    serializer_class = view_type.get_field_options_serializer_class(
        create_if_missing=False
    )
    transaction.on_commit(
        lambda: table_page_type.broadcast(
            {
                "type": "view_field_options_updated",
                "view_id": view.id,
                "field_options": serializer_class(view).data["field_options"],
            },
            getattr(user, "web_socket_id", None),
            table_id=view.table_id,
        )
    )
