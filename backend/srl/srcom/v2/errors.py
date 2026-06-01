from django.db import models
from pydantic import ValidationError as PydanticValidationError
from speedruncompy.exceptions import (
    APIException,
    BadRequest,
    ClientException,
    Forbidden,
    NotFound,
    RateLimitExceeded,
    RequestTimeout,
    ServerException,
    Unauthorized,
)


class ErrorCategory(models.TextChoices):
    AUTH = "auth", "Auth"
    API_CONTRACT = "api_contract", "API Contract"
    API_SERVER = "api_server", "API Server"
    VALIDATION = "validation", "Validation"
    RATE_LIMIT = "rate_limit", "Rate Limit"
    NETWORK = "network", "Network"
    MAILBOX = "mailbox", "Mailbox"
    UNKNOWN = "unknown", "Unknown"


def map_exception(
    exc: BaseException,
) -> ErrorCategory:
    if isinstance(exc, (Unauthorized, Forbidden)):
        return ErrorCategory.AUTH
    if isinstance(exc, RateLimitExceeded):
        return ErrorCategory.RATE_LIMIT
    if isinstance(exc, (BadRequest, NotFound)):
        return ErrorCategory.VALIDATION
    if isinstance(exc, RequestTimeout):
        return ErrorCategory.NETWORK
    if isinstance(exc, ServerException):
        return ErrorCategory.API_SERVER
    if isinstance(exc, PydanticValidationError):
        return ErrorCategory.API_CONTRACT
    if isinstance(exc, ClientException):
        return ErrorCategory.VALIDATION
    if isinstance(exc, APIException):
        return ErrorCategory.API_SERVER
    return ErrorCategory.UNKNOWN
