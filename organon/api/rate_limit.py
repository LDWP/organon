"""Shared per-IP rate limiter protecting the costly routes.

Separate from `api.app` so routers can import it without a cycle.
In-memory backend: enough while Organon runs as one process (see
`Procfile`).
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# Search autocomplete calls /search on each typing pause: wider quota.
SEARCH_RATE_LIMIT = "60/minute"
DEFAULT_RATE_LIMIT = "30/minute"
