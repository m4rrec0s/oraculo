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


def _persona_pg_conn():
    """Connect to the Hermes Postgres via ``DATABASE_URL`` (internal swarm DSN) or None."""
    try:
        import pg8000
    except ImportError:
        return None
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        return None
    try:
        # pg8000 accepts a postgres:// DSN via the `dsn` kwarg.
        return pg8000.connect(dsn=dsn)
    except Exception:
        _log.exception("Persona PG connect failed")
        return None


def _persona_sessions_query(persona: str = None, limit: int = 50, offset: int = 0):
    """Return session rows (newest activity first) or None on connect failure.

    When ``persona`` is given, only that persona's sessions are returned.
    Otherwise ALL personas are listed (admin sees everything).
    """
    conn = _persona_pg_conn()
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
        raise HTTPException(status_code=503, detail="Persona sessions store unavailable")
    return {"sessions": rows, "persona": persona, "limit": limit, "offset": offset}


@router.get("/persona-personas")
async def get_persona_personas():
    """List personas that have sessions in the store, with session counts.

    Used by the dashboard to render the persona picker before listing sessions.
    """
    conn = _persona_pg_conn()
    if conn is None:
        raise HTTPException(status_code=503, detail="Persona sessions store unavailable")
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
    conn = _persona_pg_conn()
    if conn is None:
        raise HTTPException(status_code=503, detail="Persona sessions store unavailable")
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
    conn = _persona_pg_conn()
    if conn is None:
        raise HTTPException(status_code=503, detail="Persona sessions store unavailable")
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
    conn = _persona_pg_conn()
    if conn is None:
        raise HTTPException(status_code=503, detail="Persona sessions store unavailable")
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
