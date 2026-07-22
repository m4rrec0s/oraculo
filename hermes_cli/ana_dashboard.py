"""
Persona sessions — dashboard API blueprint (isolated from core web_server.py).

All persona session routes (backed by the dedicated Hermes Postgres via
``DATABASE_URL``) live here so upstream edits to ``hermes_cli/web_server.py``
never collide with Cesto's custom surface. Register with::

    from hermes_cli.ana_dashboard import router as persona_router
    app.include_router(persona_router)
"""

import logging
import os

from fastapi import APIRouter, HTTPException, Request

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["persona"])


def _parse_pg_dsn(dsn: str) -> dict:
    """Parse a ``postgresql://`` DSN into a dict of connection kwargs."""
    import re
    m = re.match(
        r"^(?:postgres|postgresql)://(?:([^:@]+)(?::([^@]*))?@)?"
        r"([^:/]+)(?::(\d+))?/([^?]+)",
        dsn,
    )
    if not m:
        return {"user": "hermes", "host": "localhost", "port": 5432, "database": "hermes_enterprise"}
    user, password, host, port, database = m.groups()
    kwargs = {
        "user": user or "hermes",
        "host": host or "localhost",
        "port": int(port) if port else 5432,
        "database": database or "hermes_enterprise",
    }
    if password is not None:
        from urllib.parse import unquote
        kwargs["password"] = unquote(password)
    return kwargs


def _pg_connect() -> tuple:
    """Connect to Hermes Postgres. Returns ``(conn, err)``.

    Reads ``DATABASE_URL`` first, falls back to ``HERMES_PG_*`` vars.
    Uses ``pg8000.connect()`` with positional parameters (compatible with
    all pg8000 >= 1.29, avoids unsupported ``dsn=`` kwarg).
    """
    try:
        import pg8000
    except ImportError:
        _log.error("Persona PG connect failed: pg8000 not installed")
        return (None, "pg8000 driver not installed")

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        host = os.environ.get("HERMES_PG_HOST")
        if not host:
            _log.error("Persona PG connect failed: no DATABASE_URL or HERMES_PG_HOST")
            return (None, "No database URL configured (DATABASE_URL or HERMES_PG_* vars)")
        kwargs = {
            "host": host,
            "port": int(os.environ.get("HERMES_PG_PORT", "5432")),
            "database": os.environ.get("HERMES_PG_DATABASE", "hermes_enterprise"),
            "user": os.environ.get("HERMES_PG_USER", "hermes"),
        }
        pw = os.environ.get("HERMES_PG_PASSWORD", "")
        if pw:
            kwargs["password"] = pw
    else:
        kwargs = _parse_pg_dsn(dsn)

    try:
        return (pg8000.connect(**kwargs), None)
    except Exception as exc:
        _log.error("Persona PG connect failed: %s: %s", type(exc).__name__, str(exc)[:200])
        return (None, f"{type(exc).__name__}: {str(exc)[:120]}")


def _persona_pg_conn():
    """Backward-compat wrapper around _pg_connect. Used by all routes below."""
    return _pg_connect()


def _persona_sessions_query(persona: str = None, limit: int = 50, offset: int = 0):
    """Return session rows (newest activity first) or None on connect failure.

    When ``persona`` is given, only that persona's sessions are returned.
    Otherwise ALL personas are listed (admin sees everything).
    """
    conn, err = _persona_pg_conn()
    if conn is None:
        return None
    try:
        cur = conn.cursor()
        where = "WHERE s.persona = %(persona)s" if persona else ""
        cur.execute(
            f"""SELECT s.persona, s.cell, s.session_id, s.status, s.message_count,
                      COALESCE(s.metadata->>'name', c.name, s.cell) AS session_label,
                      s.last_message_at, s.created_at, s.metadata,
                      (SELECT content FROM ana_messages m
                       WHERE m.session_id = s.session_id
                       ORDER BY m.created_at DESC LIMIT 1) AS last_message
               FROM ana_sessions s
               LEFT JOIN ana_customers c ON s.cell = c.cell
               {where}
               ORDER BY s.last_message_at DESC NULLS LAST
               LIMIT %(limit)s OFFSET %(offset)s""",
            {"persona": persona, "limit": limit, "offset": offset},
        )
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return rows
    except Exception:
        _log.exception("Persona sessions query failed")
        try:
            conn.close()
        except Exception:
            pass
        return []


@router.get("/persona-sessions")
async def get_persona_sessions(persona: str = None, limit: int = 50, offset: int = 0):
    """List customer sessions from the dedicated Hermes Postgres.

    ``persona`` (query param) scopes to one persona; omit it to list ALL
    personas (admin sees every persona's sessions). Gated by the dashboard
    session token.
    """
    rows = _persona_sessions_query(persona, limit, offset)
    if rows is None:
        _, err = _persona_pg_conn()
        raise HTTPException(status_code=503, detail=f"Persona sessions store unavailable: {err or 'unknown'}")
    return {"sessions": rows, "persona": persona, "limit": limit, "offset": offset}


@router.get("/persona-personas")
async def get_persona_personas():
    """List personas that have sessions in the store, with session counts.

    Used by the dashboard to render the persona picker before listing sessions.
    """
    conn, err = _persona_pg_conn()
    if conn is None:
        raise HTTPException(status_code=503, detail=f"Persona sessions store unavailable: {err or 'unknown'}")
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT persona, COUNT(*) AS session_count
               FROM ana_sessions
               GROUP BY persona
               ORDER BY persona""",
        )
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"personas": rows}
    except Exception:
        _log.exception("Persona personas query failed")
        try:
            conn.close()
        except Exception:
            pass
        return {"personas": []}


@router.post("/persona-sessions/{session_id}/rename")
async def rename_persona_session(session_id: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    name = (body or {}).get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    conn, err = _persona_pg_conn()
    if conn is None:
        raise HTTPException(status_code=503, detail=f"Persona sessions store unavailable: {err or 'unknown'}")
    try:
        cur = conn.cursor()
        cur.execute(
            """UPDATE ana_sessions
               SET metadata = jsonb_set(COALESCE(metadata, '{}'::jsonb), '{name}', to_jsonb(%s::text))
               WHERE session_id = %s""",
            (name, session_id),
        )
        ok = cur.rowcount
        conn.commit()
        cur.close(); conn.close()
        if ok == 0:
            raise HTTPException(status_code=404, detail="session not found")
        return {"ok": True, "session_id": session_id, "name": name}
    except HTTPException:
        raise
    except Exception as exc:
        _log.exception("Persona session rename failed")
        try: conn.close()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/persona-sessions/{session_id}/toggle")
async def toggle_persona_session(session_id: str):
    conn, err = _persona_pg_conn()
    if conn is None:
        raise HTTPException(status_code=503, detail=f"Persona sessions store unavailable: {err or 'unknown'}")
    try:
        cur = conn.cursor()
        cur.execute("SELECT status FROM ana_sessions WHERE session_id = %s", (session_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="session not found")
        new = "closed" if row[0] == "active" else "active"
        cur.execute(
            "UPDATE ana_sessions SET status = %s, updated_at = NOW() WHERE session_id = %s",
            (new, session_id),
        )
        conn.commit()
        cur.close(); conn.close()
        return {"ok": True, "session_id": session_id, "status": new}
    except HTTPException:
        raise
    except Exception as exc:
        _log.exception("Persona session toggle failed")
        try: conn.close()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/persona-sessions/{session_id}/delete")
async def delete_persona_session(session_id: str):
    conn, err = _persona_pg_conn()
    if conn is None:
        raise HTTPException(status_code=503, detail=f"Persona sessions store unavailable: {err or 'unknown'}")
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM ana_messages WHERE session_id = %s", (session_id,))
        cur.execute("DELETE FROM ana_sessions WHERE session_id = %s", (session_id,))
        conn.commit()
        cur.close(); conn.close()
        return {"ok": True, "session_id": session_id}
    except Exception as exc:
        _log.exception("Persona session delete failed")
        try: conn.close()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(exc))
