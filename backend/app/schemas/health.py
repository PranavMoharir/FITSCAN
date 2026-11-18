"""Response schema for `GET /health` (LLD §4.5, decision LLD-3)."""

from typing import Literal

from pydantic import BaseModel

CheckStatus = Literal["ok", "down"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    database: CheckStatus
    redis: CheckStatus
