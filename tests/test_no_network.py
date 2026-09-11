from __future__ import annotations

import httpx
import pytest
from respx.mocks import AllMockedAssertionError


def test_requests_without_a_mock_are_blocked():
    with pytest.raises(AllMockedAssertionError):
        httpx.get("https://example.com/")


def test_requests_outside_the_api_router_are_blocked(api):
    api.get("/workspaces/acme/users").mock(return_value=httpx.Response(200, json={}))
    assert httpx.get("https://api.clarify.ai/v1/workspaces/acme/users").status_code == 200
    with pytest.raises(AllMockedAssertionError):
        httpx.get("https://api.clarify.ai/v1/workspaces/acme/other")
