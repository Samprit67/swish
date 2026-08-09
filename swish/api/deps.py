"""Request-scoped dependencies."""

from __future__ import annotations

from fastapi import Request

from swish.data.repo import Repo


def get_repo(request: Request) -> Repo:
    return request.app.state.repo
