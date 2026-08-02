from __future__ import annotations

from typing import Any


class PluginError(Exception):
    """Base class for all plugin platform errors."""

    status_code = 400
    error_code = "plugin_error"

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class PluginNotFoundError(PluginError):
    status_code = 404
    error_code = "plugin_not_found"


class PluginAlreadyInstalledError(PluginError):
    status_code = 409
    error_code = "plugin_already_installed"


class PluginInstallError(PluginError):
    status_code = 500
    error_code = "plugin_install_failed"


class PluginUninstallError(PluginError):
    status_code = 500
    error_code = "plugin_uninstall_failed"


class PluginVerificationError(PluginError):
    status_code = 422
    error_code = "plugin_verification_failed"


class PluginInvalidError(PluginError):
    status_code = 422
    error_code = "plugin_invalid"


class PluginDisabledError(PluginError):
    status_code = 409
    error_code = "plugin_disabled"


class PluginSandboxViolationError(PluginError):
    status_code = 403
    error_code = "plugin_sandbox_violation"


class PluginTimeoutError(PluginError):
    status_code = 504
    error_code = "plugin_timeout"


class PluginPermissionDeniedError(PluginError):
    status_code = 403
    error_code = "plugin_permission_denied"


class PluginSignatureError(PluginError):
    status_code = 403
    error_code = "plugin_signature_invalid"


class PluginCompatibilityError(PluginError):
    status_code = 422
    error_code = "plugin_incompatible"


class PluginUpgradeError(PluginError):
    status_code = 500
    error_code = "plugin_upgrade_failed"


class PluginRollbackError(PluginError):
    status_code = 500
    error_code = "plugin_rollback_failed"


class PluginLifecycleError(PluginError):
    status_code = 409
    error_code = "plugin_lifecycle_error"


class PluginMarketplaceError(PluginError):
    status_code = 404
    error_code = "plugin_marketplace_error"


class PluginRatingError(PluginError):
    status_code = 422
    error_code = "plugin_rating_invalid"


class PluginDependencyError(PluginError):
    status_code = 409
    error_code = "plugin_dependency_error"


class ExtensionAlreadyRegisteredError(PluginError):
    status_code = 409
    error_code = "extension_already_registered"


class ExtensionNotFoundError(PluginError):
    status_code = 404
    error_code = "extension_not_found"


class ContainerError(PluginError):
    status_code = 500
    error_code = "dependency_container_error"
