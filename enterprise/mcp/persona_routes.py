"""
Route hook for persona atendente API endpoint.

Imported by gateway/platforms/api_server.py via a single line:
    from enterprise.mcp.persona_routes import persona_route_table

This keeps the route definition outside upstream core — when upstream
changes api_server.py, only the import line conflicts (trivial to resolve).
"""

def persona_route_table(adapter):
    """Return list of (method, path, handler) tuples for persona endpoints.

    ``adapter`` is the APIServerAdapter instance; the handler closure
    captures it so ``handle_persona_message(adapter, request)`` works.
    """
    from enterprise.mcp.persona_api_handler import handle_persona_message

    return [
        ("POST", "/api/ana/message", lambda req: handle_persona_message(adapter, req)),
    ]
