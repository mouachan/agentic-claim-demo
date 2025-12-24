"""
Main FastAPI application for Claims Processing Demo.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.database import async_engine
from app.models import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    print(f"🚀 Starting {settings.app_name} v{settings.app_version}")
    print(f"📊 Environment: {settings.environment}")
    print(f"🔗 LlamaStack endpoint: {settings.llamastack_endpoint}")
    print(f"🗄️  Database: {settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}")

    yield

    # Shutdown
    print("👋 Shutting down application")
    await async_engine.dispose()


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Agentic claims processing with MCP servers and LlamaStack",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint - API information."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "status": "healthy",
    }


# Health check endpoints
@app.get("/health/live")
async def liveness():
    """Liveness probe for Kubernetes."""
    return {"status": "alive"}


@app.get("/health/ready")
async def readiness():
    """Readiness probe for Kubernetes."""
    try:
        # Test database connection
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

        return {"status": "ready", "database": "connected"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "error": str(e)},
        )


# Import and include API routers
from app.api import claims, documents

app.include_router(claims.router, prefix=f"{settings.api_v1_prefix}/claims", tags=["claims"])
app.include_router(documents.router, prefix=f"{settings.api_v1_prefix}/documents", tags=["documents"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
