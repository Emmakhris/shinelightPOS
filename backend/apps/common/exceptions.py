from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class BusinessError(Exception):
    """A business rule was broken (not enough stock, no open shift...). The message is shown to the cashier."""

    def __init__(self, message, code="business_error", http_status=status.HTTP_400_BAD_REQUEST):
        super().__init__(message)
        self.message = message
        self.code = code
        self.http_status = http_status


class ApprovalRequired(BusinessError):
    def __init__(self, message="Manager approval required."):
        super().__init__(message, code="approval_required", http_status=status.HTTP_403_FORBIDDEN)


class PinLocked(BusinessError):
    """
    Too many wrong PINs. Approvals are often checked inside a sale's database transaction, which
    this error rolls back, so anything to save goes in after_rollback and runs in the handler.
    """

    def __init__(self, message, after_rollback=None):
        super().__init__(message, code="pin_locked", http_status=status.HTTP_429_TOO_MANY_REQUESTS)
        self.after_rollback = after_rollback


def exception_handler(exc, context):
    if isinstance(exc, PinLocked) and exc.after_rollback:
        exc.after_rollback()
    if isinstance(exc, BusinessError):
        return Response({"detail": exc.message, "code": exc.code}, status=exc.http_status)
    if isinstance(exc, DjangoValidationError):
        return Response({"detail": "; ".join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
    return drf_exception_handler(exc, context)
