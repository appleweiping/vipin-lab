"""
Novelty Checker — formal duplicate detection against Semantic Scholar.

Inspired by AI Scientist v2's novelty check before proceeding.
Uses semantic similarity + exact title matching to catch duplicates.
"""
from __future__ import annotations
import re
from ..core.models import Idea
from ..providers.literature import LiteratureProvider, Paper


class NoveltyChecker:
    def __init__(self, lit: LiteratureProvider):
        self.lit = lit

    async def check(self, idea: Idea) -> tuple[bool, list[str], float]:
        """
        Check if an idea is genuinely novel.
        Returns (is_novel, blocking_papers, similarity_score).
        similarity_score: 0=completely novel, 1=exact duplicate.
        """
        # Search for papers that might duplicate this idea
        queries = [
            idea.hypothesis[:100],
            f"{idea.proposed_method[:60]} {idea.domain}",
            idea.title,
        ]
        papers = await self.lit.search_multi(queries, limit_each=8)

        if not papers:
            return True, [], 0.0

        # Check for high-similarity papers
        blocking = []
        max_sim = 0.0

        for paper in papers:
            sim = self._compute_similarity(idea, paper)
            max_sim = max(max_sim, sim)
            if sim > 0.75:
                blocking.append(
                    f"{paper.title} ({paper.year}) — similarity: {sim:.0%}"
                )

        is_novel = max_sim < 0.75 and len(blocking) == 0
        return is_novel, blocking, max_sim

    def _compute_similarity(self, idea: Idea, paper: Paper) -> float:
        """Heuristic similarity between idea and paper."""
        score = 0.0
        idea_text = f"{idea.title} {idea.hypothesis} {idea.proposed_method}".lower()
        paper_text = f"{paper.title} {paper.abstract}".lower()

        # Keyword overlap
        idea_words = set(re.findall(r'\b\w{4,}\b', idea_text))
        paper_words = set(re.findall(r'\b\w{4,}\b', paper_text))
        if idea_words and paper_words:
            overlap = len(idea_words & paper_words) / len(idea_words | paper_words)
            score += overlap * 0.6

        # Title similarity
        idea_title_words = set(re.findall(r'\b\w{4,}\b', idea.title.lower()))
        paper_title_words = set(re.findall(r'\b\w{4,}\b', paper.title.lower()))
        if idea_title_words and paper_title_words:
            title_overlap = len(idea_title_words & paper_title_words) / len(
                idea_title_words | paper_title_words
            )
            score += title_overlap * 0.4

        return min(score, 1.0)
