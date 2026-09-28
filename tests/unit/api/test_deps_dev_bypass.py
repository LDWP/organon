"""ORGANON_DEV=1 must never bypass authentication on Toolforge."""

from __future__ import annotations

from starlette.requests import Request

from organon.api.deps import get_current_username


def _anonymous_request() -> Request:
    return Request({"type": "http", "headers": []})


def test_dev_bypass_works_locally(monkeypatch):
    monkeypatch.setenv("ORGANON_DEV", "1")
    monkeypatch.delenv("TOOL_DATA_DIR", raising=False)
    assert get_current_username(_anonymous_request()) is not None


def test_dev_bypass_refused_on_toolforge(monkeypatch):
    monkeypatch.setenv("ORGANON_DEV", "1")
    monkeypatch.setenv("TOOL_DATA_DIR", "/data/project/example/data")
    assert get_current_username(_anonymous_request()) is None
