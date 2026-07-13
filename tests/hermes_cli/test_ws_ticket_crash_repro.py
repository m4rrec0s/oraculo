"""Regression test: a bad-but-present session cookie must yield a clean 401,
not an unhandled 500 (which a reverse proxy reports as 502).

Root cause: ``gated_auth_middleware`` only caught ``ProviderError`` around the
``verify_session`` call. A provider that raised ANY other exception for an
unexpected/legacy token shape (e.g. ``ValueError`` from
``int(claims["exp"])`` in ``_session_from_claims``) escaped as a 500/502,
while the no-cookie path returned a clean 401. The middleware now also catches
generic exceptions from ``verify_session``, treats them as "this provider
couldn't verify the token", and falls through to refresh / 401 — matching the
no-cookie behaviour.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from hermes_cli import web_server
from hermes_cli.dashboard_auth import clear_providers, register_provider
from tests.hermes_cli.conftest_dashboard_auth import StubAuthProvider


class BoomProvider(StubAuthProvider):
    """Provider whose ``verify_session`` raises a non-ProviderError for any
    presented token, simulating a provider that violates the verify_session
    contract (return None on invalidity; raise ProviderError only on IDP
    outage). The gate must absorb this and return 401, not crash.
    """

    def verify_session(self, *, access_token: str):
        raise ValueError("simulated legacy-token decode failure")


@pytest.fixture
def boom_app():
    clear_providers()
    register_provider(BoomProvider())
    prev_host = getattr(web_server.app.state, "bound_host", None)
    prev_port = getattr(web_server.app.state, "bound_port", None)
    prev_required = getattr(web_server.app.state, "auth_required", None)
    web_server.app.state.bound_host = "fly-app.fly.dev"
    web_server.app.state.bound_port = 443
    web_server.app.state.auth_required = True
    client = TestClient(
        web_server.app,
        base_url="https://fly-app.fly.dev",
        raise_server_exceptions=False,
    )
    yield client
    clear_providers()
    web_server.app.state.bound_host = prev_host
    web_server.app.state.bound_port = prev_port
    web_server.app.state.auth_required = prev_required


def test_bad_cookie_returns_401_not_500(boom_app):
    # Garbage session cookie present -> provider raises non-ProviderError.
    # The gate must degrade to a clean 401 (matching the no-cookie path),
    # never a 500/502 crash.
    r = boom_app.get(
        "/api/auth/me",
        cookies={
            "hermes_session_at": "garbage-token",
            "__Host-hermes_session_at": "garbage-token",
        },
    )
    assert r.status_code == 401, (
        f"Expected clean 401 for a bad cookie, got {r.status_code}: "
        f"{r.text[:300]}"
    )
    assert r.json()["error"] in ("unauthenticated", "session_expired")
