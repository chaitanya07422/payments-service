from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from payments_service.catalog import load_catalog
from payments_service.providers.polar import MockProvider, PolarProvider
from payments_service.routes import router
from payments_service.settings import get_settings
from payments_service.store import build_store


def create_app() -> FastAPI:
    settings = get_settings()
    catalog = load_catalog()
    store = build_store(settings.mongo_uri, db_name=settings.mongo_db)
    polar = PolarProvider(settings)
    mock = MockProvider()

    app = FastAPI(title="payments-service", version="0.1.0")
    app.state.settings = settings
    app.state.catalog = catalog
    app.state.store = store
    app.state.polar = polar
    app.state.mock = mock

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    @app.get("/health")
    async def root_health() -> dict:
        return {
            "ok": True,
            "service": "payments-service",
            "polar": polar.configured(),
        }

    return app


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "payments_service.main:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=False,
    )


app = create_app()
