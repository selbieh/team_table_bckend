from datetime import datetime

from django.utils import timezone
from pytz import timezone as pytz_timezone
from pytz.exceptions import UnknownTimeZoneError
from rest_framework import status, serializers
from rest_framework.exceptions import APIException

from .exceptions import (
    QueryParameterValidationException,
    RequestBodyValidationException,
)
from .utils import (
    map_exceptions as map_exceptions_utility,
    get_request,
    validate_data,
    validate_data_custom_fields,
    ExceptionMappingType,
)


def map_exceptions(exceptions: ExceptionMappingType):
    """
    This decorator simplifies mapping specific exceptions to a standard api response.
    Note that this decorator uses the map_exception function from baserow.api.utils
    which has the same name and basically does the same only this works in the form of
    a decorator.

    Example:
      @map_exceptions({ SomeException: 'ERROR_1' })
      def get(self, request):
           raise SomeException('This is a test')

      HTTP/1.1 400
      {
        "error": "ERROR_1",
        "detail": "This is a test"
      }

    Example 2:
      @map_exceptions({ SomeException: ('ERROR_1', 404, 'Other message') })
      def get(self, request):
           raise SomeException('This is a test')

      HTTP/1.1 404
      {
        "error": "ERROR_1",
        "detail": "Other message"
      }

    Example 3:
      with map_api_exceptions(
          {
              SomeException: lambda e: ('ERROR_1', 404, 'Conditional Error')
              if "something" in str(e)
              else None
          }
      ):
          raise SomeException('something')

      HTTP/1.1 404
      {
        "error": "ERROR_1",
        "detail": "Conditional Error"
      }

    Example 4:
      with map_api_exceptions(
          {
              SomeException: lambda e: ('ERROR_1', 404, 'Conditional Error')
              if "something" in str(e)
              else None
          }
      ):
          raise SomeException('doesnt match')

      # SomeException will be thrown directly if the provided callable returns None.
    """

    def map_exceptions_decorator(func):
        def func_wrapper(*args, **kwargs):
            with map_exceptions_utility(exceptions):
                return func(*args, **kwargs)

        return func_wrapper

    return map_exceptions_decorator


def validate_query_parameters(serializer: serializers.Serializer):
    """
    This decorator can validate the query parameters using a serializer. If the query
    parameters match the fields on the serializer it will add the query params to the
    kwargs. If not it will raise an APIException with structured details about what is
    wrong.

    The name of the field on the serializer must be the name of the expected query
    parameter in the query string.
    By passing "required=False" to the serializer field, we allow the query
    parameter to be unset.

    Example:
        class MoveRowQueryParamsSerializer(serializers.Serializer):
            before_id = serializers.IntegerField(required=False)

        @validate_query_parameters(MoveRowQueryParamsSerializer)
        def patch(self, request, query_params):
           raise SomeException('This is a test')

        HTTP/1.1 400
        URL: /api/database/rows/table/11/1/move/?before_id=wrong_type
        {
          "error": "ERROR_QUERY_PARAMETER_VALIDATION",
          "detail": {
            "before_id": [
              {
                "error": "A valid integer is required.",
                "code": "invalid"
              }
            ]
          }
        }

    :raises ValueError: When the `query_params` attribute is already in the kwargs. This
        decorator tries to add the `query_params` attribute, but cannot do that if it is
        already present.
    """

    def validate_decorator(func):
        def func_wrapper(*args, **kwargs):
            request = get_request(args)

            if "query_params" in kwargs:
                raise ValueError("The query_params attribute is already in the kwargs.")

            params_dict = request.GET.dict()

            kwargs["query_params"] = validate_data(
                serializer,
                params_dict,
                partial=False,
                exception_to_raise=QueryParameterValidationException,
            )

            return func(*args, **kwargs)

        return func_wrapper

    return validate_decorator


def validate_body(serializer_class, partial=False):
    """
    This decorator can validate the request body using a serializer. If the body is
    valid it will add the data to the kwargs. If not it will raise an APIException with
    structured details about what is wrong.

    Example:
        class LoginSerializer(serializers.Serializer):
            username = serializers.EmailField()
            password = serializers.CharField()

        @validate_body(LoginSerializer)
        def post(self, request):
           raise SomeException('This is a test')

        HTTP/1.1 400
        {
          "error": "ERROR_REQUEST_BODY_VALIDATION",
          "detail": {
            "username": [
              {
                "error": "This field is required.",
                "code": "required"
              }
            ]
          }
        }

    :param serializer_class: The serializer that must be used for validating.
    :param partial: Whether partial data passed to the serializer is considered valid.
    :type serializer_class: Serializer
    :raises ValueError: When the `data` attribute is already in the kwargs. This
        decorator tries to add the `data` attribute, but cannot do that if it is
        already present.
    """

    def validate_decorator(func):
        def func_wrapper(*args, **kwargs):
            request = get_request(args)

            if "data" in kwargs:
                raise ValueError("The data attribute is already in the kwargs.")

            kwargs["data"] = validate_data(serializer_class, request.data, partial)
            return func(*args, **kwargs)

        return func_wrapper

    return validate_decorator


def validate_body_custom_fields(
    registry,
    base_serializer_class=None,
    type_attribute_name="type",
    partial=False,
    allow_empty_type=False,
):
    """
    This decorator can validate the request data dynamically using the generated
    serializer that belongs to the type instance. Based on a provided
    type_attribute_name it will check the request data for a type identifier and based
    on that value it will load the type instance from the registry. With that type
    instance we know with which fields to build a serializer with that will be used.

    :param registry: The registry object where to get the type instance from.
    :type registry: Registry
    :param base_serializer_class: The base serializer class that will be used when
        generating the serializer.
    :type base_serializer_class: ModelSerializer
    :param type_attribute_name: The attribute name containing the type value in the
        request data.
    :type type_attribute_name: str
    :param partial: Whether the data is a partial update.
    :type partial: bool
    :raises RequestBodyValidationException: When the `type` is not provided.
    :raises ValueError: When the `data` attribute is already in the kwargs. This
        decorator tries to add the `data` attribute, but cannot do that if it is
        already present.
    """

    def validate_decorator(func):
        def func_wrapper(*args, **kwargs):
            request = get_request(args)
            type_name = request.data.get(type_attribute_name, None)

            if not type_name and not allow_empty_type:
                # If the type name isn't provided in the data we will raise a machine
                # readable validation error.
                raise RequestBodyValidationException(
                    {
                        type_attribute_name: [
                            {"error": "This field is required.", "code": "required"}
                        ]
                    }
                )

            if "data" in kwargs:
                raise ValueError("The data attribute is already in the kwargs.")

            kwargs["data"] = validate_data_custom_fields(
                type_name,
                registry,
                request.data,
                base_serializer_class=base_serializer_class,
                type_attribute_name=type_attribute_name,
                partial=partial,
                allow_empty_type=allow_empty_type,
            )
            return func(*args, **kwargs)

        return func_wrapper

    return validate_decorator


def allowed_includes(*allowed):
    """
    A view method decorator that checks which allowed includes are in the GET
    parameters of the request. The allowed arguments are going to be added to the
    view method kwargs and if they are in the `include` GET parameter the value will
    be True.

    Imagine this request:

    # GET /page/?include=cars,unrelated_stuff,bikes
    @allowed_includes('cars', 'bikes', 'planes')
    def get(request, cars, bikes, planes):
        cars >> True
        bikes >> True
        planes >> False

    # GET /page/?include=planes
    @allowed_includes('cars', 'bikes', 'planes')
    def get(request, cars, bikes, planes):
        cars >> False
        bikes >> False
        planes >> True

    :param allowed: Should have all the allowed include values.
    :type allowed: list
    """

    def validate_decorator(func):
        def func_wrapper(*args, **kwargs):
            request = get_request(args)
            raw_include = request.GET.get("include", None)
            includes = raw_include.split(",") if raw_include else []

            for include in allowed:
                kwargs[include] = include in includes

            return func(*args, **kwargs)

        return func_wrapper

    return validate_decorator


def accept_timezone():
    """
    This view decorator optionally accepts a timezone GET parameter. If provided, then
    the timezone is parsed via the pytz package and a now date is calculated with
    that timezone. A list of supported timezones can be found on
    https://gist.github.com/heyalexej/8bf688fd67d7199be4a1682b3eec7568.

    class SomeView(View):
        @accept_timezone()
        def get(self, request, now):
            print(now.tzinfo)

    HTTP /some-view/?timezone=Etc/GMT-1
    >>> <StaticTzInfo 'Etc/GMT-1'>
    """

    def validate_decorator(func):
        def func_wrapper(*args, **kwargs):
            request = get_request(args)

            timezone_string = request.GET.get("timezone")

            try:
                kwargs["now"] = (
                    datetime.utcnow().astimezone(pytz_timezone(timezone_string))
                    if timezone_string
                    else timezone.now()
                )
            except UnknownTimeZoneError:
                exc = APIException(
                    {
                        "error": "UNKNOWN_TIME_ZONE_ERROR",
                        "detail": f"The timezone {timezone_string} is not supported. A "
                        f"list of support timezones can be found on "
                        f"https://gist.github.com/heyalexej/8bf688fd67d7199be4a1682b3e"
                        f"ec7568.",
                    }
                )
                exc.status_code = status.HTTP_400_BAD_REQUEST
                raise exc

            return func(*args, **kwargs)

        return func_wrapper

    return validate_decorator
