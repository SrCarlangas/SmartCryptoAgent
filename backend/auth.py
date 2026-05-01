"""Auth placeholder.

Por ahora no hay autenticación: el backend bind a 127.0.0.1 y el acceso es
vía SSH tunnel. Cuando se publique el panel, aquí entra HTTP Basic / JWT.
"""
from fastapi import Request


async def noop_auth(request: Request):
    """Dependency stub que siempre permite."""
    return True
