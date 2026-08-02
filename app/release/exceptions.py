"""Exceptions for the release subsystem."""

from __future__ import annotations


class ReleaseError(Exception):
    """Base class for release subsystem errors."""


class VersionError(ReleaseError):
    """Invalid or malformed semantic version."""


class VersionNotFoundError(ReleaseError):
    """Requested version does not exist in history."""


class ChangelogError(ReleaseError):
    """Changelog generation or parsing failed."""


class SigningError(ReleaseError):
    """Signature creation or verification failed."""


class SignatureVerificationError(SigningError):
    """Signature did not verify against the provided key."""


class PublishError(ReleaseError):
    """Publishing to a registry/channel failed."""


class ReleaseLockedError(ReleaseError):
    """The release has already been finalised or is immutable."""
