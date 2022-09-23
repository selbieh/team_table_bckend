import os

import pytest
from django.core.management import call_command
from django.db import DEFAULT_DB_ALIAS

SKIP_FLAGS = ["disabled-in-ci", "once-per-day-in-ci"]
COMMAND_LINE_FLAG_PREFIX = "--run-"


@pytest.fixture
def data_fixture():
    from .fixtures import Fixtures

    return Fixtures()


@pytest.fixture()
def api_client():
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture(scope="module")
def reset_schema_after_module(request, django_db_setup, django_db_blocker):
    yield
    with django_db_blocker.unblock():
        call_command("migrate", verbosity=0, database=DEFAULT_DB_ALIAS)


@pytest.fixture()
def environ():
    original_env = os.environ.copy()
    yield os.environ
    for key, value in original_env.items():
        os.environ[key] = value


@pytest.fixture()
def mutable_field_type_registry():
    from baserow.contrib.database.fields.registries import field_type_registry

    before = field_type_registry.registry.copy()
    yield field_type_registry
    field_type_registry.registry = before


@pytest.fixture()
def mutable_action_registry():
    from baserow.core.action.registries import action_type_registry

    before = action_type_registry.registry.copy()
    yield action_type_registry
    action_type_registry.registry = before


# We reuse this file in the premium backend folder, if you run a pytest session over
# plugins and the core at the same time pytest will crash if this called multiple times.
def pytest_addoption(parser):
    # Unfortunately a simple decorator doesn't work here as pytest is doing some
    # exciting reflection of sorts over this function and crashes if it is wrapped.
    if not hasattr(pytest_addoption, "already_run"):
        for flag in SKIP_FLAGS:
            parser.addoption(
                f"{COMMAND_LINE_FLAG_PREFIX}{flag}",
                action="store_true",
                default=False,
                help=f"run {flag} tests",
            )
        pytest_addoption.already_run = True


def pytest_configure(config):
    if not hasattr(pytest_configure, "already_run"):
        for flag in SKIP_FLAGS:
            config.addinivalue_line(
                "markers",
                f"{flag}: mark test so it only runs when the "
                f"{COMMAND_LINE_FLAG_PREFIX}{flag} flag is provided to pytest",
            )
        pytest_configure.already_run = True


def pytest_collection_modifyitems(config, items):
    enabled_flags = {
        flag
        for flag in SKIP_FLAGS
        if config.getoption(f"{COMMAND_LINE_FLAG_PREFIX}{flag}")
    }
    for item in items:
        for flag in SKIP_FLAGS:
            flag_for_python = flag.replace("-", "_")
            if flag_for_python in item.keywords and flag not in enabled_flags:
                skip_marker = pytest.mark.skip(
                    reason=f"need {COMMAND_LINE_FLAG_PREFIX}{flag} option to run"
                )
                item.add_marker(skip_marker)
                break
