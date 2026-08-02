"""Exceptions for the deployment subsystem."""

from __future__ import annotations


class DeployError(Exception):
    """Base class for deployment pipeline errors."""


class QualityGateError(DeployError):
    """A quality gate threshold was not met."""


class SmokeTestError(DeployError):
    """A smoke test failed."""


class RollbackTestError(DeployError):
    """A rollback test failed."""


class VerificationError(DeployError):
    """Post-deployment verification failed."""


class GitOpsError(DeployError):
    """GitOps manifest validation or application failed."""


class SigningGateError(DeployError):
    """Artifact signature verification failed."""
