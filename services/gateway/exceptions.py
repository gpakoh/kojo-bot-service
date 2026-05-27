"""Gateway exceptions for circuit breaker exclusion."""


class GatewayProviderError(Exception):
    """Base exception for gateway provider errors.

    Subclass this for specific transient errors that should NOT
    trip the circuit breaker (e.g., 4xx client errors vs 5xx server errors).
    """


class GatewayTransientError(GatewayProviderError):
    """Transient errors that should not trip the circuit breaker.

    Examples: 400 Bad Request, 401 Unauthorized, 404 Not Found.
    These are client errors, not server failures.
    """


class GatewayServerError(GatewayProviderError):
    """Server errors that SHOULD trip the circuit breaker.

    Examples: 502 Bad Gateway, 503 Service Unavailable, timeouts.
    These indicate the upstream service is actually failing.
    """
