from __future__ import annotations


class CruisewiseError(Exception):
    """Base for all application-level errors."""


class NotFoundError(CruisewiseError):
    """Resource does not exist."""


class ValidationError(CruisewiseError):
    """Input failed domain-level validation (distinct from Pydantic's own)."""


class InventoryError(CruisewiseError):
    """Cruise inventory source returned an unexpected response."""


class NoSailingsFound(CruisewiseError):
    """No sailings matched the intake, or all sub-agent calls failed."""


class RepriceError(CruisewiseError):
    """Reprice analysis could not be completed."""


class NotifierError(CruisewiseError):
    """Notification delivery failed."""
