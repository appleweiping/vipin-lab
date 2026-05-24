"""
Phenomenon Observatory Engine.

The core differentiator: instead of starting from keywords, we start from
observed anomalies, contradictions, and unexplained results in the literature.

A phenomenon is: "Method X consistently underperforms on Y despite theoretical
guarantees" or "Metric A and Metric B diverge in domain Z" or "Model size
doesn't help beyond N for task T."

This engine:
1. Scans literature for anomalies and contradictions
2. Scores phenomenon severity (how important is this gap?)
3. Generates hypotheses about root causes
4. Ranks phenomena by research potential
"""
from __future__ import annotations
import json
import re
from ..core.models import Phenomenon
from ..core.config import LabConfig
from ..providers.llm import LLMProvider
from ..providers.literature import LiteratureProvider, Paper


PHENOMENON_DETECTION_PROMPT = """You are a scientific anomaly detector. Your job is to find phenomena —
observed anomalies, contradictions, unexplained results, and performance gaps in the research literature.

Domain: {domain}
Recent papers:
{papers}

A phenomenon is NOT a research gap ("nobody has done X"). A phenomenon IS:
- "Method X consistently underperforms on Y despite theoretical guarantees"
- "Metric A and Metric B diverge in domain Z — models that rank well on A rank poorly on B"
- "Model size doesn't help beyond N for task T, but nobody knows why"
- "Technique X works in domain A but fails in domain B despite similar structure"
- "Baseline Y is surprisingly competitive with recent methods on metric Z"
- "Performance degrades sharply at rank position K across all LLM recommenders"

For each phenomenon you find, output a JSON object:
{{
  "description": "precise description of the anomaly",
  "evidence": ["paper1 title", "paper2 title"],
  "unexplained_by": ["existing method 1", "existing method 2"],
  "potential_causes": ["hypothesis 1", "hypothesis 2", "hypothesis 3"],
  "severity": 0.0-1.0,
  "research_potential": "why this is worth investigating"
}}

Output a JSON array of phenomena. Find at most 5, but only include real ones with evidence.
If you don't find genuine phenomena, return an empty array [].
"""

PHENOMENON_RANKING_PROMPT = """You are evaluating research phenomena for their scientific value.

Domain: {domain}
Phenomena found:
{phenomena}

For each phenomenon, score it on:
1. Severity (0-10): How important is this gap to the field?
2. Novelty (0-10): How unexplored is this phenomenon?
3. Tractability (0-10): How feasible is it to investigate this?
4. Impact (0-10): If solved, how much would it advance the field?

Output JSON array:
[{{"id": 0, "severity": X, "novelty": X, "tractability": X, "impact": X, "verdict": "pursue/monitor/skip"}}]
"""


class PhenomenonObservatory:
    def __init__(self, config: LabConfig, llm: LLMProvider, lit: LiteratureProvider):
        self.config = config
        self.llm = llm
        self.lit = lit

    async def scan(self, domain: str, n_papers: int = 30) -> list[Phenomenon]:
        """Scan a domain for phenomena. Returns ranked list."""
        # Gather recent papers from multiple angles
        queries = [
            f"{domain} limitations failure cases",
            f"{domain} performance gap analysis",
            f"{domain} contradictions inconsistencies",
            f"{domain} surprising results unexpected",
            f"{domain} benchmark evaluation 2024 2025",
        ]
        papers = await self.lit.search_multi(queries, limit_each=8)
        papers = sorted(papers, key=lambda p: p.citation_count, reverse=True)[:n_papers]

        if not papers:
            return []

        paper_text = self.lit.format_for_prompt(papers, max_papers=20)

        # Detect phenomena
        response = await self.llm.complete(
            self.config.architect(),
            [{"role": "user", "content": PHENOMENON_DETECTION_PROMPT.format(
                domain=domain, papers=paper_text
            )}],
            temperature=0.4,
            max_tokens=4096,
        )

        raw_phenomena = self._parse_json_array(response)
        if not raw_phenomena:
            return []

        # Score and rank
        phenomena_text = json.dumps(raw_phenomena, indent=2)
        ranking_response = await self.llm.complete(
            self.config.auditor(),
            [{"role": "user", "content": PHENOMENON_RANKING_PROMPT.format(
                domain=domain, phenomena=phenomena_text
            )}],
            temperature=0.2,
            max_tokens=2048,
        )
        rankings = self._parse_json_array(ranking_response)

        # Build Phenomenon objects
        result = []
        import uuid
        for i, raw in enumerate(raw_phenomena):
            rank = next((r for r in rankings if r.get("id") == i), {})
            severity = rank.get("severity", 5) / 10.0
            verdict = rank.get("verdict", "monitor")

            if verdict == "skip" or severity < self.config.phenomenon_severity_threshold:
                continue

            p = Phenomenon(
                id=str(uuid.uuid4())[:8],
                domain=domain,
                description=raw.get("description", ""),
                evidence=raw.get("evidence", []),
                unexplained_by=raw.get("unexplained_by", []),
                potential_causes=raw.get("potential_causes", []),
                severity=severity,
                source_papers=[p.paper_id for p in papers[:5]],
            )
            result.append(p)

        # Sort by severity
        result.sort(key=lambda x: x.severity, reverse=True)
        return result[:self.config.max_phenomena_per_session]

    def _parse_json_array(self, text: str) -> list[dict]:
        """Extract JSON array from LLM response."""
        # Try to find JSON array in the response
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        # Try the whole text
        try:
            result = json.loads(text.strip())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
        return []
