import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import API_PREFIX, get_settings
from .logging_setup import configure_logging
from .routers import core, feeds, sources, teams

settings = get_settings()
configure_logging(settings.log_level)
access_log = logging.getLogger("gridline.access")

# Vercel forwards the original /api path. root_path keeps those routes compatible
# with the unprefixed paths used by local development and Docker.
app = FastAPI(title="GRIDLINE API", version="0.2.0", description="GRIDLINE motorsport calendar API", root_path=API_PREFIX)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["content-type", "x-edit-token", "if-none-match"],
    expose_headers=["etag", "retry-after"],
)


@app.middleware("http")
async def request_log(request: Request, call_next):
    """Log request metadata without query strings, headers, or tokens."""
    start = time.monotonic()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        access_log.info("request", extra={
            "method": request.method, "path": request.url.path, "status": status,
            "duration_ms": int((time.monotonic() - start) * 1000),
        })


for r in (core.router, teams.router, feeds.router, sources.router):
    app.include_router(r)
