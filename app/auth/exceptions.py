from __future__ import annotations


class AuthError(Exception):
    pass


class AuthenticationError(AuthError):
    pass


class InvalidCredentialsError(AuthenticationError):
    pass


class AccountLockedError(AuthenticationError):
    def __init__(self, locked_until: float):
        super().__init__("Account is locked")
        self.locked_until = locked_until


class AccountInactiveError(AuthenticationError):
    pass


class MFARequiredError(AuthenticationError):
    pass


class InvalidTokenError(AuthError):
    pass


class TokenExpiredError(InvalidTokenError):
    pass


class TokenRevokedError(InvalidTokenError):
    pass


class SessionExpiredError(AuthError):
    pass


class SessionLimitError(AuthError):
    pass


class APIKeyError(AuthError):
    pass


class ServiceAccountError(AuthError):
    pass


class PermissionDeniedError(AuthError):
    def __init__(self, permission: str, user_id: str = ""):
        super().__init__(f"Permission {permission!r} denied for user {user_id!r}")
        self.permission = permission
        self.user_id = user_id


class ProviderError(AuthError):
    pass


class ProviderNotFoundError(AuthError):
    def __init__(self, name: str):
        super().__init__(f"Auth provider {name!r} is not registered")
        self.name = name
