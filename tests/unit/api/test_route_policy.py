"""Politique unique : toute route /api/v1 qui fait des appels réseau exige une session et un
rate-limit ; les routes locales (catalogues, auth) en sont exemptées."""

from __future__ import annotations

from types import ModuleType

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute

from organon.api.app import app
from organon.api.deps import require_username
from organon.api.rate_limit import limiter
from organon.api.routes import (
    auth,
    commons_images,
    domains,
    generate,
    modules,
    search,
    sources,
    subtaxa_merge,
    taxobox_refresh,
    update,
)

NETWORK_ROUTERS = [
    commons_images,
    generate,
    search,
    subtaxa_merge,
    taxobox_refresh,
    update,
]
LOCAL_ROUTERS = [auth, domains, modules, sources]
NETWORK_ROUTES = [r for m in NETWORK_ROUTERS for r in m.router.routes if isinstance(r, APIRoute)]
# Routes declared directly on the app, with no third-party call.
LOCAL_APP_PATHS = {"/api/v1/version"}
# The OAuth callback calls Wikimedia but runs before any session exists: rate-limit only.
PRE_SESSION_NETWORK_ENDPOINTS = {auth.callback}


def _qualname(route: APIRoute) -> str:
    return f"{route.endpoint.__module__}.{route.endpoint.__name__}"


def _unclassified_api_routes(target: FastAPI) -> set[tuple[str, str]]:
    """(method, path) published under /api/v1 by `target` but declared by no classified router.

    Reads the OpenAPI schema: FastAPI keeps included routers lazy, so `target.routes` is no
    longer a flat list of routes.
    """
    classified = {
        (method, f"/api/v1{r.path}")
        for m in NETWORK_ROUTERS + LOCAL_ROUTERS
        for r in m.router.routes
        if isinstance(r, APIRoute)
        for method in r.methods
    }
    published = {
        (method.upper(), path)
        for path, operations in target.openapi()["paths"].items()
        if path.startswith("/api/v1/")
        for method in operations
    }
    return published - classified - {("GET", p) for p in LOCAL_APP_PATHS}


@pytest.mark.parametrize("route", NETWORK_ROUTES, ids=lambda r: f"{sorted(r.methods)} {r.path}")
def test_network_route_requires_session_and_rate_limit(route: APIRoute) -> None:
    assert require_username in {d.call for d in route.dependant.dependencies}
    assert _qualname(route) in limiter._route_limits


@pytest.mark.parametrize("endpoint", PRE_SESSION_NETWORK_ENDPOINTS, ids=lambda e: e.__name__)
def test_pre_session_network_endpoint_is_rate_limited(endpoint) -> None:
    assert f"{endpoint.__module__}.{endpoint.__name__}" in limiter._route_limits


def test_every_mounted_api_route_is_classified() -> None:
    assert _unclassified_api_routes(app) == set()


def test_unclassified_router_is_detected() -> None:
    rogue = APIRouter()

    @rogue.get("/rogue")
    async def rogue_route() -> dict:
        return {}

    probe = FastAPI()
    probe.include_router(rogue, prefix="/api/v1")
    assert _unclassified_api_routes(probe) == {("GET", "/api/v1/rogue")}


def test_no_router_is_both_network_and_local() -> None:
    both: set[ModuleType] = set(NETWORK_ROUTERS) & set(LOCAL_ROUTERS)
    assert both == set()
