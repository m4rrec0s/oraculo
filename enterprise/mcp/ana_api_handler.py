"""
HTTP handler for POST /api/ana/message — the Ana atendente inbound endpoint.

Extracted from gateway/platforms/api_server.py. The API server registers
this as a route via the hook in enterprise/mcp/ana_routes.py.
"""
import re
import logging
from typing import TYPE_CHECKING

from enterprise.mcp.ana_pg_store import (
    ana_idle_seconds,
    ana_pg_session_id,
    load_ana_session_from_pg,
    load_ana_history_from_pg,
    persist_ana_turn,
    reset_ana_session_in_pg,
)

if TYPE_CHECKING:
    from aiohttp import web

logger = logging.getLogger(__name__)

_MAX_SESSION_HEADER_LEN = 200


def _openai_error(message: str, code: str = "error") -> dict:
    return {"error": {"message": message, "type": "invalid_request_error", "code": code}}


async def handle_ana_message(adapter, request: "web.Request") -> "web.Response":
    """POST /api/ana/message — inbound turn for the Ana atendente.

    ``adapter`` is the APIServerAdapter instance (provides _check_auth,
    _read_json_body, _run_agent, config, gateway_runner).
    """
    from aiohttp import web

    auth_err = adapter._check_auth(request)
    if auth_err:
        return auth_err
    body, err = await adapter._read_json_body(request)
    if err:
        return err

    session_key = body.get("sessionKey") or body.get("session_key")
    message = body.get("message")
    push_name = body.get("pushName") or body.get("push_name")

    if not session_key or not str(session_key).strip():
        return web.json_response(
            _openai_error("Missing 'sessionKey'", code="missing_session_key"),
            status=400,
        )
    if not isinstance(message, str) or not message.strip():
        return web.json_response(
            _openai_error("Missing 'message'", code="missing_message"),
            status=400,
        )

    safe_key = re.sub(r"[\r\n\x00]", "", str(session_key)).strip()
    if len(safe_key) > _MAX_SESSION_HEADER_LEN:
        safe_key = safe_key[:_MAX_SESSION_HEADER_LEN]
    if not safe_key:
        return web.json_response(
            _openai_error("Invalid sessionKey", code="invalid_session_key"),
            status=400,
        )
    sid = ana_pg_session_id(safe_key)

    # 72h idle TTL
    idle_minutes = 4320
    runner = getattr(adapter, "gateway_runner", None)
    cfg = getattr(runner, "config", None)
    if cfg is not None:
        try:
            from gateway.platforms.base import Platform
            pol = cfg.get_reset_policy(platform=Platform.API_SERVER)
            if pol and getattr(pol, "mode", "none") != "none":
                idle_minutes = getattr(pol, "idle_minutes", idle_minutes)
        except Exception:
            pass

    pg_session = load_ana_session_from_pg(sid)
    if pg_session and ana_idle_seconds(
        pg_session.get("updated_at") or pg_session.get("created_at")
    ) > idle_minutes * 60:
        reset_ana_session_in_pg(sid)
        pg_session = None

    history = load_ana_history_from_pg(sid)

    ephemeral_system_prompt = None
    if push_name:
        ephemeral_system_prompt = (
            f"O(a) cliente desta conversa se chama {push_name}. "
            "Use o nome dele(a) para personalizar o atendimento quando fizer sentido."
        )

    result, _usage = await adapter._run_agent(
        user_message=message,
        conversation_history=history,
        ephemeral_system_prompt=ephemeral_system_prompt,
        session_id=sid,
        gateway_session_key=session_key,
    )
    final_response = result.get("final_response", "") if isinstance(result, dict) else ""

    if adapter.config.extra.get("use_postgres", True):
        try:
            import asyncio as _asyncio
            loop = _asyncio.get_event_loop()
            await loop.run_in_executor(
                None, persist_ana_turn, safe_key, message, final_response, push_name,
            )
        except Exception:
            logger.debug("Ana turn persist failed", exc_info=True)

    return web.json_response({
        "object": "hermes.ana.message",
        "sessionKey": session_key,
        "pushName": push_name,
        "message": {"role": "assistant", "content": final_response},
    })
