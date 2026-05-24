"""
Tool Registry — pluggable tools for agents.

Inspired by AI-Researcher's tool retrieval system.
Agents can call tools by name; the registry handles routing.

Available tools:
- web_search: search the web for recent papers/news
- semantic_scholar: search academic papers
- arxiv_fetch: fetch full paper abstract from arXiv ID
- code_exec: execute Python code in a sandbox (read-only analysis)
- file_read: read a file from the workspace
- file_write: write a file to the workspace
"""
from __future__ import annotations
import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Awaitable
import httpx


@dataclass
class ToolResult:
    tool: str
    success: bool
    output: str
    error: str = ""


ToolFn = Callable[[dict], Awaitable[ToolResult]]


class ToolRegistry:
    def __init__(self, workspace_dir: str = "", semantic_scholar_key: str = ""):
        self._tools: dict[str, ToolFn] = {}
        self._workspace = Path(workspace_dir) if workspace_dir else Path(".")
        self._ss_key = semantic_scholar_key
        self._register_defaults()

    def register(self, name: str, fn: ToolFn):
        self._tools[name] = fn

    async def call(self, name: str, args: dict) -> ToolResult:
        if name not in self._tools:
            return ToolResult(tool=name, success=False, output="",
                              error=f"Unknown tool: {name}. Available: {list(self._tools)}")
        try:
            return await self._tools[name](args)
        except Exception as e:
            return ToolResult(tool=name, success=False, output="", error=str(e))

    def list_tools(self) -> list[dict]:
        return [
            {"name": name, "description": fn.__doc__ or ""}
            for name, fn in self._tools.items()
        ]

    def _register_defaults(self):
        self.register("semantic_scholar", self._semantic_scholar)
        self.register("arxiv_fetch", self._arxiv_fetch)
        self.register("file_read", self._file_read)
        self.register("file_write", self._file_write)
        self.register("web_search", self._web_search)

    async def _semantic_scholar(self, args: dict) -> ToolResult:
        """Search Semantic Scholar for papers. Args: {query, limit=10, year_from=2020}"""
        query = args.get("query", "")
        limit = min(int(args.get("limit", 10)), 20)
        year_from = args.get("year_from", 2020)
        params = {
            "query": query, "limit": limit,
            "fields": "title,abstract,year,venue,citationCount,tldr",
            "year": f"{year_from}-",
        }
        headers = {"x-api-key": self._ss_key} if self._ss_key else {}
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params=params, headers=headers,
            )
            r.raise_for_status()
            data = r.json()
        papers = data.get("data", [])
        lines = []
        for p in papers:
            tldr = p.get("tldr", {})
            tldr_text = tldr.get("text", "") if tldr else ""
            lines.append(
                f"[{p.get('year', '?')}] {p.get('title', '')} "
                f"({p.get('venue', 'arXiv')}, {p.get('citationCount', 0)} cites)\n"
                f"  {(p.get('abstract') or '')[:150]}..."
                + (f"\n  TL;DR: {tldr_text}" if tldr_text else "")
            )
        return ToolResult(tool="semantic_scholar", success=True,
                          output="\n\n".join(lines) if lines else "No results found")

    async def _arxiv_fetch(self, args: dict) -> ToolResult:
        """Fetch paper details from arXiv. Args: {arxiv_id}"""
        arxiv_id = args.get("arxiv_id", "").strip()
        if not arxiv_id:
            return ToolResult(tool="arxiv_fetch", success=False, output="",
                              error="arxiv_id required")
        url = f"https://export.arxiv.org/abs/{arxiv_id}"
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(url)
            r.raise_for_status()
        # Extract title and abstract from HTML
        title_match = re.search(r'<h1[^>]*class="title[^"]*"[^>]*>(.*?)</h1>', r.text, re.DOTALL)
        abstract_match = re.search(r'<blockquote[^>]*class="abstract[^"]*"[^>]*>(.*?)</blockquote>',
                                   r.text, re.DOTALL)
        title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip() if title_match else arxiv_id
        abstract = re.sub(r'<[^>]+>', '', abstract_match.group(1)).strip() if abstract_match else ""
        return ToolResult(tool="arxiv_fetch", success=True,
                          output=f"Title: {title}\n\nAbstract: {abstract}")

    async def _file_read(self, args: dict) -> ToolResult:
        """Read a file from the workspace. Args: {path}"""
        rel_path = args.get("path", "")
        full_path = self._workspace / rel_path
        if not full_path.exists():
            return ToolResult(tool="file_read", success=False, output="",
                              error=f"File not found: {rel_path}")
        content = full_path.read_text(encoding="utf-8", errors="replace")
        return ToolResult(tool="file_read", success=True,
                          output=content[:8000])  # cap at 8K chars

    async def _file_write(self, args: dict) -> ToolResult:
        """Write a file to the workspace. Args: {path, content}"""
        rel_path = args.get("path", "")
        content = args.get("content", "")
        if not rel_path:
            return ToolResult(tool="file_write", success=False, output="",
                              error="path required")
        full_path = self._workspace / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        return ToolResult(tool="file_write", success=True,
                          output=f"Written {len(content)} chars to {rel_path}")

    async def _web_search(self, args: dict) -> ToolResult:
        """Search the web via DuckDuckGo. Args: {query, max_results=5}"""
        query = args.get("query", "")
        max_results = min(int(args.get("max_results", 5)), 10)
        # Use DuckDuckGo HTML search (no API key needed)
        url = "https://html.duckduckgo.com/html/"
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            r = await client.post(url, data={"q": query},
                                  headers={"User-Agent": "Mozilla/5.0"})
        # Extract result snippets
        results = re.findall(
            r'<a[^>]+class="result__a"[^>]*>(.*?)</a>.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
            r.text, re.DOTALL
        )
        lines = []
        for title, snippet in results[:max_results]:
            title_clean = re.sub(r'<[^>]+>', '', title).strip()
            snippet_clean = re.sub(r'<[^>]+>', '', snippet).strip()
            lines.append(f"• {title_clean}\n  {snippet_clean}")
        return ToolResult(tool="web_search", success=True,
                          output="\n\n".join(lines) if lines else "No results found")
