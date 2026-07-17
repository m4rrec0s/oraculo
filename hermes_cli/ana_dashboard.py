"""
Ana Atendimento — dashboard API blueprint (isolated from core web_server.py).

All Ana session routes (backed by the dedicated Hermes Postgres via
``HERMES_PG_*``) live here so upstream edits to ``hermes_cli/web_server.py``
never collide with Cesto's custom surface. Register with::

    from hermes_cli.ana_dashboard import router as ana_router
    app.include_router(ana_router)
"""

import logging
import os

from fastapi import APIRouter, HTTPException, Request

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["ana"])


def _ana_pg_conn():
    """Connect to the dedicated Hermes Postgres (``HERMES_PG_*``) or None."""
    try:
        import pg8000
    except ImportError:
        return None
    host = os.environ.get("HERMES_PG_HOST")
    if not host:
        return None
    try:
        return pg8000.connect(
            host=host,
            port=int(os.environ.get("HERMES_PG_PORT", "5432")),
            database=os.environ.get("HERMES_PG_DATABASE", "hermes_enterprise"),
            user=os.environ.get("HERMES_PG_USER", "hermes"),
            password=os.environ.get("HERMES_PG_PASSWORD", ""),
        )
    except Exception:
        _log.exception("Ana PG connect failed")
        return None


def _ana_sessions_query(limit: int = 50, offset: int = 0):
    """Return Ana session rows (newest activity first) or None on connect failure."""
    conn = _ana_pg_conn()
    if conn is None:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT s.cell, s.session_id, s.status, s.message_count,
                      COALESCE(s.metadata->>'name', c.name, s.cell) AS session_label,
                      s.last_message_at, s.created_at, s.metadata,
                      (SELECT content FROM ana_messages m
                       WHERE m.session_id = s.session_id
                       ORDER BY m.created_at DESC LIMIT 1) AS last_message
               FROM ana_sessions s
               LEFT JOIN ana_customers c ON s.cell = c.cell
               ORDER BY s.last_message_at DESC NULLS LAST
               LIMIT %s OFFSET %s""",
            (limit, offset),
        )
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return rows
    except Exception:
        _log.exception("Ana sessions query failed")
        try:
            conn.close()
        except Exception:
            pass
        return []


@router.get("/ana-sessions")
async def get_ana_sessions(limit: int = 50, offset: int = 0):
    """List Ana customer sessions from the dedicated Hermes Postgres.

    Gated by the dashboard session token (not in ``public_paths``). External
    automations (n8n/Express) query the same data directly via ``HERMES_PG_*``.
    """
    rows = _ana_sessions_query(limit, offset)
    if rows is None:
        raise HTTPException(status_code=503, detail="Ana sessions store unavailable")
    return {"sessions": rows, "limit": limit, "offset": offset}


@router.post("/ana-sessions/{session_id}/rename")
async def rename_ana_session(session_id: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    name = (body or {}).get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    conn = _ana_pg_conn()
    if conn is None:
        raise HTTPException(status_code=503, detail="Ana sessions store unavailable")
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
        _log.exception("Ana session rename failed")
        try: conn.close()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/ana-sessions/{session_id}/toggle")
async def toggle_ana_session(session_id: str):
    conn = _ana_pg_conn()
    if conn is None:
        raise HTTPException(status_code=503, detail="Ana sessions store unavailable")
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
        _log.exception("Ana session toggle failed")
        try: conn.close()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/ana-sessions/{session_id}/delete")
async def delete_ana_session(session_id: str):
    conn = _ana_pg_conn()
    if conn is None:
        raise HTTPException(status_code=503, detail="Ana sessions store unavailable")
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM ana_messages WHERE session_id = %s", (session_id,))
        cur.execute("DELETE FROM ana_sessions WHERE session_id = %s", (session_id,))
        conn.commit()
        cur.close(); conn.close()
        return {"ok": True, "session_id": session_id}
    except Exception as exc:
        _log.exception("Ana session delete failed")
        try: conn.close()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(exc))
