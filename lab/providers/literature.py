"""Literature provider — Semantic Scholar + arXiv search."""
from __future__ import annotations
import asyncio
import httpx
from dataclasses import dataclass


@dataclass
class Paper:
    title: str
    abstract: str
    authors: list[str]
    year: int
    venue: str
    paper_id: str
    url: str
    citation_count: int = 0
    tldr: str = ""


class LiteratureProvider:
    SS_BASE = "https://api.semanticscholar.org/graph/v1"
    ARXIV_BASE = "https://export.arxiv.org/api/query"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self._headers = {"x-api-key": api_key} if api_key else {}

    async def search(self, query: str, limit: int = 20, year_from: int = 2020) -> list[Paper]:
        """Search Semantic Scholar for papers matching query."""
        params = {
            "query": query,
            "limit": limit,
            "fields": "title,abstract,authors,year,venue,externalIds,citationCount,tldr",
            "year": f"{year_from}-",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                r = await client.get(
                    f"{self.SS_BASE}/paper/search",
                    params=params,
                    headers=self._headers,
                )
                r.raise_for_status()
                data = r.json()
                papers = []
                for p in data.get("data", []):
                    papers.append(Paper(
                        title=p.get("title", ""),
                        abstract=p.get("abstract", "") or "",
                        authors=[a.get("name", "") for a in p.get("authors", [])],
                        year=p.get("year") or 0,
                        venue=p.get("venue", "") or "",
                        paper_id=p.get("paperId", ""),
                        url=f"https://www.semanticscholar.org/paper/{p.get('paperId', '')}",
                        citation_count=p.get("citationCount", 0),
                        tldr=p.get("tldr", {}).get("text", "") if p.get("tldr") else "",
                    ))
                return papers
            except Exception:
                return []

    async def get_paper(self, paper_id: str) -> Paper | None:
        """Get full details for a specific paper."""
        fields = "title,abstract,authors,year,venue,citationCount,references,citations,tldr"
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                r = await client.get(
                    f"{self.SS_BASE}/paper/{paper_id}",
                    params={"fields": fields},
                    headers=self._headers,
                )
                r.raise_for_status()
                p = r.json()
                return Paper(
                    title=p.get("title", ""),
                    abstract=p.get("abstract", "") or "",
                    authors=[a.get("name", "") for a in p.get("authors", [])],
                    year=p.get("year") or 0,
                    venue=p.get("venue", "") or "",
                    paper_id=paper_id,
                    url=f"https://www.semanticscholar.org/paper/{paper_id}",
                    citation_count=p.get("citationCount", 0),
                    tldr=p.get("tldr", {}).get("text", "") if p.get("tldr") else "",
                )
            except Exception:
                return None

    async def search_multi(self, queries: list[str], limit_each: int = 10) -> list[Paper]:
        """Run multiple searches in parallel and deduplicate."""
        results = await asyncio.gather(*[self.search(q, limit_each) for q in queries])
        seen = set()
        papers = []
        for batch in results:
            for p in batch:
                if p.paper_id not in seen:
                    seen.add(p.paper_id)
                    papers.append(p)
        return papers

    def format_for_prompt(self, papers: list[Paper], max_papers: int = 10) -> str:
        """Format papers as a compact string for LLM prompts."""
        lines = []
        for i, p in enumerate(papers[:max_papers]):
            tldr = f" | {p.tldr}" if p.tldr else ""
            lines.append(
                f"[{i+1}] {p.title} ({p.year}, {p.venue or 'arXiv'}, {p.citation_count} cites){tldr}\n"
                f"    {p.abstract[:200]}..."
            )
        return "\n\n".join(lines)
