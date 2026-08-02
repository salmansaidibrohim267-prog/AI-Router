"""Exceptions for the observability subsystem."""

from __future__ import annotations


class ObservabilityError(Exception):
    """Base class for observability errors."""


class SloError(ObservabilityError):
    """Invalid SLO definition or computation."""


class AlertingError(ObservabilityError):
    """Alert rule definition or evaluation failure."""


class DashboardError(ObservabilityError):
    """Dashboard generation or serialisation failure."""
