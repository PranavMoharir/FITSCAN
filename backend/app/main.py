"""Creates the FastAPI application: routers, CORS and error handlers (LLD §4.2).

Run locally from the `backend/` folder:  uvicorn app.main:app --reload
OpenAPI docs are generated automatically at /docs and /openapi.json.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import background_jobs, health
from app.config import get_settings
from app.errors import register_error_handlers


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Job–Candidate Matching Platform API",
        version="0.1.0",
        description="Crawls jobs, parses resumes and matches candidates to jobs.",
    )

    # Only the configured frontend origin may call the API from a browser (HLD §12.1).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    register_error_handlers(app)

    app.include_router(health.router)
    app.include_router(background_jobs.router)
    return app


app = create_app()
