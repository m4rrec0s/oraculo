"""
Postgres-backed session store for atendente personas.

Extracted from gateway/platforms/api_server.py to keep Oraculo-specific
code outside the upstream core. This module is imported by the API server
via a thin hook — when upstream changes, only the hook import line conflicts.
"""
import json as _json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


def idle_seconds(ts: Any) -> float:
    """Idle time (seconds) since a session timestamp; 0.0 if unknown."""
    if ts is None:
        return 0.0
    if isinstance(ts, (int, float)):
        try:
            return time.time() - float(ts)
        except (TypeError, ValueError):
            return 0.0
    if isinstance(ts, str):
        s = ts.strip()
        try:
            return time.time() - float(s)
        except ValueError:
            pass
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()
        except Exception:
            return 0.0
    return 0.0


def pg_connect_kwargs() -> Optional[dict]:
    """Return connection kwargs from DATABASE_URL or HERMES_PG_* vars.

    Returns ``None`` when neither source is configured.
    """
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        m = re.match(
            r"^(?:postgres|postgresql)://(?:([^:@]+)(?::([^@]*))?@)?"
            r"([^:/]+)(?::(\d+))?/([^?]+)",
            dsn,
        )
        if m:
            user, password, host, port, database = m.groups()
            kwargs: dict = {
                "user": user or "hermes",
                "host": host or "localhost",
                "port": int(port) if port else 5432,
                "database": database or "hermes_enterprise",
            }
            if password is not None:
                from urllib.parse import unquote
                kwargs["password"] = unquote(password)
            return kwargs
            logger.warning("persona persist: DATABASE_URL parse failed, trying HERMES_PG_*")
    host = os.environ.get("HERMES_PG_HOST")
    if not host:
        return None
    return {
        "host": host,
        "port": int(os.environ.get("HERMES_PG_PORT", "5432")),
        "database": os.environ.get("HERMES_PG_DATABASE", "hermes_enterprise"),
        "user": os.environ.get("HERMES_PG_USER", "hermes"),
        "password": os.environ.get("HERMES_PG_PASSWORD"),
    }


def pg_session_id(session_key: str) -> str:
    """Canonical Postgres session_id for an Ana persona turn.

    Matches the ``{persona}_{session_key}`` convention.
    """
    persona = os.environ.get("ENTERPRISE_PROFILE", "atendimento")
    return f"{persona}_{session_key}"


def persist_turn(session_key: str, user_msg: str, assistant_msg: str, push_name: str | None = None) -> None:
    """Upsert the persona session + append user/assistant messages to the
    dedicated Hermes Postgres (``DATABASE_URL`` — internal swarm DSN).
    Best-effort: any failure is swallowed so a DB hiccup never breaks the
    customer turn."""
    try:
        import pg8000
    except ImportError:
        logger.debug("ana persist skipped: pg8000 not installed")
        return
    kwargs = pg_connect_kwargs()
    if kwargs is None:
        logger.debug("ana persist skipped: no DATABASE_URL or HERMES_PG_* vars")
        return
    persona = os.environ.get("ENTERPRISE_PROFILE", "atendimento")
    cell = re.sub(r"\D", "", str(session_key))[:20]
    sid = f"{persona}_{session_key}"
    try:
        conn = pg8000.connect(**kwargs)
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO sessions (persona, cell, session_id, status, last_message_at, message_count, updated_at, metadata)
               VALUES (%s, %s, %s, 'active', NOW(), 1, NOW(), %s)
               ON CONFLICT (session_id) DO UPDATE SET
                 persona = %s,
                 last_message_at = NOW(), updated_at = NOW(),
                 message_count = sessions.message_count + 1,
                 status = CASE WHEN sessions.status = 'archived' THEN 'active' ELSE sessions.status END""",
            (persona, cell, sid, _json.dumps({"name": push_name}) if push_name else None, persona),
        )
        cur.execute(
            """INSERT INTO messages (persona, session_id, role, content, created_at)
               VALUES (%s, %s, 'user', %s, NOW()),
                      (%s, %s, 'assistant', %s, NOW())""",
            (persona, sid, user_msg, persona, sid, assistant_msg),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as exc:
        logger.debug("ana persist error: %s", exc)


def load_session_from_pg(session_id: str) -> Optional[dict]:
    """Fetch session metadata from dedicated Hermes Postgres.

    Returns a dict with ``updated_at`` / ``created_at`` as float epochs,
    or ``None`` when unavailable / not found.
    """
    try:
        import pg8000
    except ImportError:
        return None
    kwargs = pg_connect_kwargs()
    if kwargs is None:
        return None
    try:
        conn = pg8000.connect(**kwargs)
        cur = conn.cursor()
        cur.execute(
            "SELECT updated_at, created_at FROM sessions WHERE session_id = %s",
            (session_id,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row is None:
            return None
        import datetime as _dt
        result: dict = {}
        for idx, key in enumerate(("updated_at", "created_at")):
            val = row[idx]
            if val is None:
                result[key] = 0.0
            elif isinstance(val, _dt.datetime):
                result[key] = val.timestamp()
            else:
                result[key] = float(val)
        return result
    except Exception as exc:
        logger.debug("ana PG session lookup failed: %s", exc)
        return None


def load_history_from_pg(session_id: str) -> list:
    """Load conversation history for an Ana session from dedicated Postgres.

    Returns a list of ``{"role": ..., "content": ..., "timestamp": ...}``
    dicts compatible with ``_run_agent(conversation_history=...)``.
    """
    try:
        import pg8000
    except ImportError:
        return []
    kwargs = pg_connect_kwargs()
    if kwargs is None:
        return []
    try:
        conn = pg8000.connect(**kwargs)
        cur = conn.cursor()
        cur.execute(
            """SELECT role, content, created_at
               FROM messages
               WHERE session_id = %s
               ORDER BY created_at ASC""",
            (session_id,),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        import datetime as _dt
        history: list = []
        for role, content, ts in rows:
            if isinstance(ts, _dt.datetime):
                epoch = ts.timestamp()
            elif ts is None:
                epoch = 0.0
            else:
                epoch = float(ts)
            history.append({"role": role, "content": content, "timestamp": epoch})
        return history
    except Exception as exc:
        logger.debug("ana PG history load failed: %s", exc)
        return []


def session_exists_in_pg(session_id: str) -> bool:
    """Return True if the session row exists in dedicated Postgres."""
    try:
        import pg8000
    except ImportError:
        return False
    kwargs = pg_connect_kwargs()
    if kwargs is None:
        return False
    try:
        conn = pg8000.connect(**kwargs)
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM sessions WHERE session_id = %s LIMIT 1",
            (session_id,),
        )
        found = cur.fetchone() is not None
        cur.close()
        conn.close()
        return found
    except Exception as exc:
        logger.debug("ana PG existence check failed: %s", exc)
        return False


def reset_session_in_pg(session_id: str) -> None:
    """Delete session + messages from Postgres (idle timeout reset)."""
    try:
        import pg8000 as _pg
        _kw = pg_connect_kwargs()
        if _kw:
            _conn = _pg.connect(**_kw)
            _cur = _conn.cursor()
            _cur.execute("DELETE FROM messages WHERE session_id = %s", (session_id,))
            _cur.execute("DELETE FROM sessions WHERE session_id = %s", (session_id,))
            _conn.commit()
            _cur.close()
            _conn.close()
    except Exception:
        logger.debug("Ana PG session reset failed for %s", session_id, exc_info=True)
