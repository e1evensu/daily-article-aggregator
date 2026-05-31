import ssl

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings

def build_ssl_context() -> ssl.SSLContext:
    """Build the MySQL TLS context from explicit repository settings.

    The default keeps the current deployment behavior: encrypted transport with
    self-signed server certs accepted. Turning `DATABASE_VERIFY_TLS` on requires
    a verifiable certificate chain and hostname match.
    """
    ctx = ssl.create_default_context()
    if settings.database_verify_tls:
        return ctx
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


# DB lives in CN (114); app in EU (38). The autossh tunnel is a single SSH
# channel that wedges under load over the lossy cross-border link (measured
# 0/3 connects). We connect direct to 114:3306 instead (firewall already
# restricts 3306 to 38 only), wrapped in MySQL TLS so the wire stays encrypted.
_ssl_ctx = build_ssl_context()

engine = create_async_engine(
    settings.database_url,
    echo=settings.log_level == "debug",
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_recycle=settings.database_pool_recycle_s,
    # pre_ping refreshes connections gone stale on the long-haul link instead of
    # hanging; connect_timeout bounds a stuck connect.
    pool_pre_ping=True,
    connect_args={"connect_timeout": 20, "ssl": _ssl_ctx},
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session():
    """Yield one async SQLAlchemy session outside the FastAPI dependency layer."""
    async with async_session() as session:
        yield session


async def warm_pool() -> int:
    """Pre-open pool connections sequentially so the first user requests don't
    each eat a cold cross-border connect (~4-13s). Holds each open until all are
    made, then releases them live back to the pool. Returns the number warmed."""
    from sqlalchemy import text

    held = []
    warmed = 0
    try:
        for _ in range(settings.database_pool_size):
            try:
                conn = await engine.connect()
                await conn.execute(text("SELECT 1"))
                held.append(conn)
                warmed += 1
            except Exception:
                break  # link saturated; lazy creation covers the rest
    finally:
        for conn in held:
            await conn.close()
    return warmed
