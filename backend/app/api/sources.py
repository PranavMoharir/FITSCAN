"""/sources: the job sources the crawler supports (LLD §4.5, §5.16). Read-only, from the extractor registry."""

from fastapi import APIRouter

from app.extractors.registry import get_registry
from app.schemas.source import SourceInfo, SourceList

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get(
    "", response_model=SourceList, summary="Supported job sources",
    description="One entry per extractor. `kind` tells real sources (company career pages and job boards) from "
                "demo sites, whose invented jobs are always labelled demo. A crawl uses a source by its seed URL, "
                "or names it in `extractor`. Only sites that may be crawled are reached: robots.txt, the domain "
                "allow-list and the private-address guard apply to every source.",
)
def list_sources() -> SourceList:
    return SourceList(items=[
        SourceInfo(
            name=e.name, label=e.label, description=e.description, kind="demo" if e.demo else "real",
            hosts=list(e.domains), formats=list(e.formats), needs_browser=e.render_mode == "browser",
            seed_template=e.seed_template, seed_key_label=e.seed_key_label, example_seed=e.example_seed,
        )
        for e in get_registry().extractors
    ])
