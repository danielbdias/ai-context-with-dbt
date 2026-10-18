"""FastAPI application factory."""

import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from web.db import make_pool
from web.logs import configure_logging, log_event
from web.routes import router
from web.settings import Settings

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


async def handle_request(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Add request id, security headers and a JSON access log line.

    Unhandled errors are turned into a bare 500 and only the exception class
    is logged: driver errors can quote the row that failed, message included.
    """
    request_id = uuid.uuid4().hex
    request.state.request_id = request_id
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        log_event("unhandled_error", request_id=request_id, error=type(exc).__name__)
        response = PlainTextResponse("Internal Server Error", status_code=500)
    response.headers.update(SECURITY_HEADERS)
    response.headers["X-Request-ID"] = request_id
    log_event(
        "request",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
    )
    return response


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app; settings default to the environment."""
    configure_logging()
    resolved = settings or Settings()  # type: ignore[call-arg]

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        pool = make_pool(resolved)
        pool.open(wait=False)
        app.state.pool = pool
        yield
        pool.close()

    app = FastAPI(
        title="Demo submissions",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = resolved
    app.middleware("http")(handle_request)
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"))
    app.include_router(router)
    return app
