"""
Route hook for the Ana atendente API endpoint.

Imported by gateway/platforms/api_server.py via a single line:
    from enterprise.mcp.ana_routes import ana_route_table

This keeps the route definition outside upstream core — when upstream
changes api_server.py, only the import line conflicts (trivial to resolve).
"""

def ana_route_table(adapter):
    """Return list of (method, path, handler) tuples for Ana endpoints.

    ``adapter`` is the APIServerAdapter instance; the handler closure
    captures it so ``handle_ana_message(adapter, request)`` works.
    """
    from enterprise.mcp.ana_api_handler import handle_ana_message

    return [
        ("POST", "/api/ana/message", lambda req: handle_ana_message(adapter, req)),
    ]
