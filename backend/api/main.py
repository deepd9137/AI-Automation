from backend.core.config import settings
from backend.core.logging import configure_logging
from backend.routes.health import router as health_router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

configure_logging()


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Engagement Assistant",
        version=settings.APP_VERSION,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )
    app.include_router(health_router, prefix="/api/v1")
    return app


app = create_app()
