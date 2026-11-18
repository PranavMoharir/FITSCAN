"""`GET /health`: is the API able to reach PostgreSQL and Redis? (LLD §4.5, decision LLD-3)

Docker's health check reads only the status code (200 or 503). The body tells a person
which dependency is down. Each check has a short timeout, so a hanging service makes
the check fail quickly instead of hanging it.
"""

import logging
from concurrent.futures import Future, ThreadPoolExecutor, wait

import redis
from fastapi import APIRouter

from app.config import get_settings
from app.db.session import check_database
from app.errors import AppError
from app.schemas.common import ErrorResponse
from app.schemas.health import CheckStatus, HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

REDIS_TIMEOUT_SECONDS = 3
# Upper limit for the whole endpoint. The connection timeouts do not cover the DNS lookup:
# inside Docker, looking up a stopped service ("db", "redis") takes about 4 seconds to fail.
HEALTH_CHECK_DEADLINE_SECONDS = 3


def check_redis() -> bool:
    """Return True if Redis answers PING within the timeout."""
    client = redis.Redis.from_url(
        get_settings().redis_url,
        socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
        socket_timeout=REDIS_TIMEOUT_SECONDS,
    )
    try:
        return bool(client.ping())
    except (redis.RedisError, OSError) as exc:
        logger.warning("Redis check failed: %s", exc.__class__.__name__)
        return False
    finally:
        client.close()


def _passed(check: Future) -> bool:
    """A check passes only if it finished in time, without an error, and returned True."""
    return check.done() and check.exception() is None and check.result() is True


def run_checks() -> tuple[bool, bool]:
    """Run both checks at the same time and wait at most HEALTH_CHECK_DEADLINE_SECONDS.

    A check still running at the deadline counts as down. Its thread finishes in the
    background (each check has its own timeouts) and the result is discarded.
    """
    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="health-check")
    try:
        database = executor.submit(check_database)
        broker = executor.submit(check_redis)
        wait([database, broker], timeout=HEALTH_CHECK_DEADLINE_SECONDS)
        return _passed(database), _passed(broker)
    finally:
        executor.shutdown(wait=False)


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": ErrorResponse, "description": "PostgreSQL or Redis is unreachable"}},
    summary="Database and Redis reachability",
)
def health() -> HealthResponse:
    database_ok, redis_ok = run_checks()
    database: CheckStatus = "ok" if database_ok else "down"
    redis_status: CheckStatus = "ok" if redis_ok else "down"
    if database == "ok" and redis_status == "ok":
        return HealthResponse(status="ok", database=database, redis=redis_status)
    raise AppError(
        status_code=503,
        code="SERVICE_UNAVAILABLE",
        message="Service temporarily unavailable.",
        details={"database": database, "redis": redis_status},
    )
