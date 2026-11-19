"""Schemas shared by all endpoints: the error envelope (HLD §12.1) and the list and filter conventions (LLD §4.4)."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, Field

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100  # the bounded maximum of every paginated list

SortOrder = Literal["asc", "desc"]
ExportFormat = Literal["csv", "json"]
Number = int | float  # numeric columns as JSON numbers: 3, not "3" or 3.0


def blank_to_none(value: Any) -> Any:
    """Search boxes send "" when empty: a blank filter is no filter. Other text is trimmed."""
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


# A free-text filter: trimmed, blank means "not set", at most 200 characters. The length limit
# belongs to the text alone: applied to the whole optional type, it would fail on the None that a
# blank value becomes.
SearchText = Annotated[Annotated[str, Field(max_length=200)] | None, BeforeValidator(blank_to_none)]


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
