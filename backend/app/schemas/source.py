"""GET /sources: the job sources the crawler supports, one per extractor plug-in (LLD §4.5, §5.16)."""

from typing import Literal

from pydantic import BaseModel, Field


class SourceInfo(BaseModel):
    name: str = Field(description="Stored as jobs.source; the crawl request's `extractor`", examples=["greenhouse"])
    label: str = Field(examples=["Greenhouse job board"])
    description: str
    kind: Literal["real", "demo"] = Field(description="demo: a demo site with invented jobs, never real openings")
    hosts: list[str] = Field(description="The hosts this source reads (empty: any host, the generic fallback)")
    formats: list[Literal["html", "json"]] = Field(description="What it reads: HTML pages or a JSON API")
    needs_browser: bool = Field(description="True if its pages are rendered in a headless browser")
    seed_template: str | None = Field(
        description="The seed URL with one {key} to fill in, for job-board APIs",
        examples=["https://boards-api.greenhouse.io/v1/boards/{key}/jobs?content=true"])
    seed_key_label: str | None = Field(description="What {key} is", examples=["Board token"])
    example_seed: str | None = Field(description="An example seed URL, for sources without a template")


class SourceList(BaseModel):
    """Real sources first, then demo ones."""

    items: list[SourceInfo]
