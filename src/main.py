import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from src.api import items, digests, sources, runs, stats
from src.api.contracts import request_id
from src.db import engine, warm_pool

log = logging.getLogger("uvicorn.error")


async def _warm_pool_bg():
    """Warm database connections asynchronously so API startup stays non-blocking."""
    try:
        warmed = await warm_pool()
        log.info("DB pool warmed: %d connections", warmed)
    except Exception as exc:
        log.warning("DB pool warmup failed (continuing): %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background warmup on boot and dispose the engine on shutdown."""
    # Warm the cross-border pool in the background so startup is instant; first
    # requests may be slow until the pool fills, but the app serves immediately.
    task = asyncio.create_task(_warm_pool_bg())
    yield
    task.cancel()
    await engine.dispose()


app = FastAPI(title="Intelligence System", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    """Attach or propagate a request id and echo it back to the caller."""
    request.state.request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    response = await call_next(request)
    response.headers["x-request-id"] = request.state.request_id
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Normalize FastAPI HTTP errors into the project envelope shape."""
    if isinstance(exc.detail, dict) and "code" in exc.detail and "message" in exc.detail:
        error = exc.detail
    else:
        error = {"code": "http_error", "message": str(exc.detail)}
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": error, "meta": {"request_id": request_id(request)}},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Hide internal exceptions behind a stable 500 error contract."""
    return JSONResponse(
        status_code=500,
        content={
            "error": {"code": "internal_error", "message": "Internal server error"},
            "meta": {"request_id": request_id(request)},
        },
    )

app.include_router(items.router, prefix="/api/v1")
app.include_router(digests.router, prefix="/api/v1")
app.include_router(sources.router, prefix="/api/v1")
app.include_router(runs.router, prefix="/api/v1")
app.include_router(stats.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}
