from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


WIDGET_PATHS = {"/api/v1/chat/init", "/api/v1/chat"}


class WidgetCORSMiddleware(BaseHTTPMiddleware):
    """Libera CORS de transporte somente para as rotas públicas do widget."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path not in WIDGET_PATHS:
            return await call_next(request)

        origin = request.headers.get("origin")
        if request.method == "OPTIONS":
            response = Response(status_code=204)
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = request.headers.get(
                "access-control-request-headers", "Authorization, Content-Type, X-Tenant-ID"
            )
        else:
            response = await call_next(request)

        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers.add_vary_header("Origin")

        return response