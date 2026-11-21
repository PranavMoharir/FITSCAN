"""Creates the FastAPI application: routers, CORS and error handlers (LLD §4.2).

Run locally from the `backend/` folder:  uvicorn app.main:app --reload
OpenAPI docs are generated automatically at /docs and /openapi.json.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import background_jobs, candidates, exports, health, jobs, matching, skills
from app.api.upload_limit import RequestTooLarge, UploadSizeLimit, handle_request_too_large
from app.config import get_settings
from app.errors import register_error_handlers


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Job–Candidate Matching Platform API",
        version="0.1.0",
        description="Crawls jobs, parses resumes and matches candidates to jobs.",
    )

    # A total size limit for resume uploads, checked while the request streams in. Added before
    # CORS, so CORS wraps it and a browser can read its 422 answer.
    app.add_middleware(UploadSizeLimit)
    # Only the configured frontend origin may call the API from a browser (HLD §12.1).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    register_error_handlers(app)
    app.add_exception_handler(RequestTooLarge, handle_request_too_large)

    app.include_router(health.router)
    app.include_router(background_jobs.router)
    app.include_router(jobs.router)
    app.include_router(candidates.router)
    app.include_router(skills.router)
    app.include_router(exports.router)
    app.include_router(matching.router)
    return app


app = create_app()
