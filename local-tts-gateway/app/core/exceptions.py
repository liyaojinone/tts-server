class GatewayError(Exception):
    code = "INTERNAL_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ProviderNotFoundError(GatewayError):
    code = "PROVIDER_NOT_FOUND"


class ModelNotFoundError(GatewayError):
    code = "MODEL_NOT_FOUND"


class ProviderDisabledError(GatewayError):
    code = "PROVIDER_DISABLED"


class ProviderStartTimeoutError(GatewayError):
    code = "PROVIDER_START_TIMEOUT"


class ProviderUnavailableError(GatewayError):
    code = "PROVIDER_UNAVAILABLE"
