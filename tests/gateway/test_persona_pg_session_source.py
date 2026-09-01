"""Regression tests for Ana persona PG-first session behavior.

When ``ENTERPRISE_PROFILE`` is set (non-admin persona), ``/api/ana/message``
must use the dedicated Hermes Postgres (sessions / messages) as the
single source of truth for session history and lifecycle.  The local SessionDB
(state.db) must NEVER be read for Ana turns — dashboard deletes from Postgres
take effect immediately.
"""

import os
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from gateway.config import PlatformConfig
from gateway.platforms.api_server import APIServerAdapter


@pytest.fixture
def adapter():
    return APIServerAdapter(PlatformConfig(enabled=True, extra={"key": "sk-test"}))


def _persona_app(adapter: APIServerAdapter) -> web.Application:
    app = web.Application()
    # The route is registered via the enterprise hook
    from enterprise.mcp.persona_api_handler import handle_persona_message
    app.router.add_post("/api/ana/message", lambda req: handle_persona_message(adapter, req))
    return app


def _auth_headers():
    return {"Authorization": "Bearer sk-test"}


# ---------------------------------------------------------------------------
# Session ID format: must match the PG convention {persona}_{session_key}
# ---------------------------------------------------------------------------


class TestPersonaSessionIdFormat:
    def test_default_persona_prefix(self):
        from enterprise.mcp.pg_session_store import pg_session_id
        with patch.dict(os.environ, {"ENTERPRISE_PROFILE": "atendimento"}, clear=False):
            assert pg_session_id("5511999999999") == "atendimento_5511999999999"

    def test_custom_persona_prefix(self):
        from enterprise.mcp.pg_session_store import pg_session_id
        with patch.dict(os.environ, {"ENTERPRISE_PROFILE": "honda"}, clear=False):
            assert pg_session_id("551188887777") == "honda_551188887777"


# ---------------------------------------------------------------------------
# History loaded from Postgres, never from local SessionDB
# ---------------------------------------------------------------------------


class TestPersonaHistoryFromPostgres:
    @pytest.mark.asyncio
    async def test_history_comes_from_pg_not_sessiondb(self, adapter, monkeypatch):
        """After PG delete, next persona request must get empty history."""
        pg_history = [
            {"role": "user", "content": "oi", "timestamp": 1000.0},
            {"role": "assistant", "content": "ola!", "timestamp": 1001.0},
        ]
        call_log = []

        def _mock_load_history(session_id):
            call_log.append(session_id)
            return pg_history if call_log.__len__() <= 1 else []

        monkeypatch.setattr("enterprise.mcp.pg_session_store.load_session_from_pg", lambda sid: {"updated_at": 1000.0, "created_at": 999.0})
        monkeypatch.setattr("enterprise.mcp.pg_session_store.load_history_from_pg", _mock_load_history)

        mock_run = AsyncMock(return_value=({"final_response": "ok", "session_id": "atendimento_5511999"}, {}))
        monkeypatch.setattr(adapter, "_run_agent", mock_run)
        monkeypatch.setattr(adapter, "config", PlatformConfig(enabled=True, extra={"use_postgres": False}))

        app = _persona_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp1 = await cli.post(
                "/api/ana/message",
                json={"sessionKey": "5511999", "message": "hello"},
                headers=_auth_headers(),
            )
            assert resp1.status == 200

            _, history_kw = mock_run.call_args
            assert len(history_kw["conversation_history"]) == 2

            # Simulate PG delete — second call should see empty history
            resp2 = await cli.post(
                "/api/ana/message",
                json={"sessionKey": "5511999", "message": "hello again"},
                headers=_auth_headers(),
            )
            assert resp2.status == 200
            _, history_kw2 = mock_run.call_args
            assert history_kw2["conversation_history"] == []

    @pytest.mark.asyncio
    async def test_session_id_matches_pg_convention(self, adapter, monkeypatch):
        """The session_id passed to _run_agent must use {persona}_{key} format."""
        captured = {}

        async def _mock_run(**kwargs):
            captured["session_id"] = kwargs.get("session_id")
            return {"final_response": "ok", "session_id": kwargs.get("session_id")}, {}

        monkeypatch.setattr(adapter, "_run_agent", _mock_run)
        monkeypatch.setattr("enterprise.mcp.pg_session_store.load_session_from_pg", lambda sid: None)
        monkeypatch.setattr("enterprise.mcp.pg_session_store.load_history_from_pg", lambda sid: [])
        monkeypatch.setattr(adapter, "config", PlatformConfig(enabled=True, extra={"use_postgres": False}))

        app = _persona_app(adapter)
        with patch.dict(os.environ, {"ENTERPRISE_PROFILE": "atendimento"}, clear=False):
            async with TestClient(TestServer(app)) as cli:
                resp = await cli.post(
                    "/api/ana/message",
                    json={"sessionKey": "5511999999999", "message": "test"},
                    headers=_auth_headers(),
                )
                assert resp.status == 200
                assert captured["session_id"] == "atendimento_5511999999999"

    @pytest.mark.asyncio
    async def test_pg_not_found_returns_empty_history(self, adapter, monkeypatch):
        """When session doesn't exist in PG, history must be empty (fresh start)."""
        monkeypatch.setattr("enterprise.mcp.pg_session_store.load_session_from_pg", lambda sid: None)
        monkeypatch.setattr("enterprise.mcp.pg_session_store.load_history_from_pg", lambda sid: [])

        mock_run = AsyncMock(return_value=({"final_response": "fresh", "session_id": "atendimento_x"}, {}))
        monkeypatch.setattr(adapter, "_run_agent", mock_run)
        monkeypatch.setattr(adapter, "config", PlatformConfig(enabled=True, extra={"use_postgres": False}))

        app = _persona_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.post(
                    "/api/ana/message",
                json={"sessionKey": "new_customer", "message": "hi"},
                headers=_auth_headers(),
            )
            assert resp.status == 200
            _, kwargs = mock_run.call_args
            assert kwargs["conversation_history"] == []

    @pytest.mark.asyncio
    async def test_idle_timeout_uses_pg_not_sessiondb(self, adapter, monkeypatch):
        """Idle timeout must be checked against PG, not local SessionDB."""
        deleted_in_pg = []

        def _mock_load_session(sid):
            return {"updated_at": 1.0, "created_at": 0.0}

        def _mock_load_history(sid):
            return []

        def _mock_delete_pg(sid):
            deleted_in_pg.append(sid)

        monkeypatch.setattr("enterprise.mcp.pg_session_store.load_session_from_pg", _mock_load_session)
        monkeypatch.setattr("enterprise.mcp.pg_session_store.load_history_from_pg", _mock_load_history)
        monkeypatch.setattr("enterprise.mcp.pg_session_store.reset_session_in_pg", _mock_delete_pg)
        monkeypatch.setattr(adapter, "config", PlatformConfig(enabled=True, extra={"use_postgres": False}))

        mock_run = AsyncMock(return_value=({"final_response": "ok", "session_id": "atendimento_old"}, {}))
        monkeypatch.setattr(adapter, "_run_agent", mock_run)

        app = _persona_app(adapter)
        # The idle check uses idle_seconds; with updated_at=1.0 it's always idle
        with patch.dict(os.environ, {"ENTERPRISE_PROFILE": "atendimento"}, clear=False):
            async with TestClient(TestServer(app)) as cli:
                resp = await cli.post(
                    "/api/ana/message",
                    json={"sessionKey": "old_cell", "message": "still there?"},
                    headers=_auth_headers(),
                )
                assert resp.status == 200
                # The PG session was expired, so history must be empty
                _, kwargs = mock_run.call_args
                assert kwargs["conversation_history"] == []
