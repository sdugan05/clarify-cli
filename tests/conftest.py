"""Shared fixtures: isolated config/env, a respx router, and a CliRunner helper."""

from __future__ import annotations

import pytest
import respx
from typer.testing import CliRunner

from clarify_cli.main import app

BASE_URL = "https://api.clarify.ai/v1"
WS = f"{BASE_URL}/workspaces/acme"


@pytest.fixture(autouse=True)
def no_network():
    """Fail loudly if a test lets a request escape its mocks.

    respx consults routers in registration order, so this empty router is the
    fallback for every test: a request no ``api`` (or ad-hoc) router handles
    raises ``AllMockedAssertionError`` instead of reaching the real network.
    """
    with respx.mock(assert_all_mocked=True, assert_all_called=False):
        yield


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Point config at a temp file, provide fake credentials, and disable sleeping."""
    monkeypatch.setenv("CLARIFY_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.setenv("CLARIFY_API_KEY", "test-key")
    monkeypatch.setenv("CLARIFY_WORKSPACE", "acme")
    for var in ("CLARIFY_BASE_URL", "CLARIFY_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("clarify_cli.client.time.sleep", lambda _s: None)
    return tmp_path


@pytest.fixture
def api():
    """A respx router mounted at the API base URL. Unmatched requests fail loudly."""
    with respx.mock(base_url=BASE_URL, assert_all_called=False, assert_all_mocked=True) as router:
        yield router


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def invoke(runner):
    """Run the root app: ``invoke("users", "list", "-n", 5)``."""

    def _invoke(*args, input: str | None = None):
        return runner.invoke(app, [str(a) for a in args], input=input)

    return _invoke
