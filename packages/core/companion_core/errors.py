"""Typed errors with stable machine-readable codes.

Services map these to HTTP responses; the desk UI keys its messages off ``code``.
"""

from __future__ import annotations


class CompanionError(Exception):
    code = "internal_error"
    http_status = 500

    def __init__(self, message: str | None = None, *, details: dict | None = None) -> None:
        super().__init__(message or self.code)
        self.message = message or self.code
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "details": self.details}


class ConfigError(CompanionError):
    code = "config_error"
    http_status = 500


class AuthenticationError(CompanionError):
    code = "unauthenticated"
    http_status = 401


class PermissionDenied(CompanionError):
    code = "permission_denied"
    http_status = 403


class NotFound(CompanionError):
    code = "not_found"
    http_status = 404


class ValidationFailed(CompanionError):
    code = "validation_failed"
    http_status = 422


class Conflict(CompanionError):
    code = "conflict"
    http_status = 409


class UpstreamUnavailable(CompanionError):
    """A dependency (Ollama, Home Assistant, vault) could not be reached in time."""

    code = "upstream_unavailable"
    http_status = 503


class UpstreamError(CompanionError):
    code = "upstream_error"
    http_status = 502


class NotConfigured(CompanionError):
    """A feature exists but its integration is disabled or missing credentials."""

    code = "not_configured"
    http_status = 501


class Cancelled(CompanionError):
    code = "cancelled"
    http_status = 499
