"""The web layer: a thin FastAPI wrapper over :mod:`swish.model`."""

from swish.api.app import create_app

__all__ = ["create_app"]
