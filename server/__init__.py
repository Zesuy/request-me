"""QQ-facing request-me server."""

from .app import create_app
from .core import RequestService

__all__ = ["RequestService", "create_app"]
