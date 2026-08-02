"""Exceptions for the migration subsystem."""

from __future__ import annotations


class MigrationError(Exception):
    """Base class for migration errors."""


class MigrationNotFoundError(MigrationError):
    """Requested migration does not exist."""


class MigrationConflictError(MigrationError):
    """A migration with the same name/version already exists."""


class MigrationVersionError(MigrationError):
    """Version ordering or tracking inconsistency."""


class MigrationLockedError(MigrationError):
    """The schema is locked by another process."""


class MigrationFailureError(MigrationError):
    """An up/down step raised during execution."""
