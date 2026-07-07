"""
Content Marketing Engine — FastAPI Application Entry Point.

Provides the FastAPI app instance with CORS middleware, health check endpoint,
and module routers mounted under the /api/v1 prefix.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.auth.router import router as auth_router
from app.products.segment_router import router as segments_router
from app.products.product_router import router as product_router
from app.products.document_router import router as document_router
from app.products.claim_router import router as claim_router
from app.products.version_router import router as version_router
from app.llm.generation_router import router as generation_router
from app.settings.user_management_router import router as user_management_router
from app.settings.brand_rules_router import router as brand_rules_router
from app.settings.llm_router import router as settings_llm_router
from app.rate_limiter import limiter

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle handler."""
    logger.info("Starting Content Marketing Engine...")
    yield
    logger.info("Shutting down Content Marketing Engine...")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title="Content Marketing Engine",
        description="LLM-powered marketing content generation platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS — allow frontend dev server; restrict in production via environment
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate limiting — global limiter with IP-based keys
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # Mount API routers
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(segments_router, prefix="/api/v1")
    app.include_router(product_router, prefix="/api/v1")
    app.include_router(document_router, prefix="/api/v1")
    app.include_router(claim_router, prefix="/api/v1")
    app.include_router(version_router, prefix="/api/v1")
    app.include_router(generation_router, prefix="/api/v1")
    app.include_router(user_management_router, prefix="/api/v1")
    app.include_router(brand_rules_router, prefix="/api/v1")
    app.include_router(settings_llm_router, prefix="/api/v1")

    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Return service health status."""
        return {"status": "healthy", "version": app.version}

    return app


app: FastAPI = create_app()
