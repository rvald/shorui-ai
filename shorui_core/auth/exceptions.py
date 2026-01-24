"""
Auth-specific exceptions.
"""

from shorui_core.domain.exceptions import ShoruiError


class AuthError(ShoruiError):
    """Base authentication/authorization error."""

    pass


class InvalidApiKeyError(AuthError):
    """Raised when API key is invalid or expired."""

    pass


class InsufficientScopesError(AuthError):
    """Raised when user lacks required permissions."""

    pass
