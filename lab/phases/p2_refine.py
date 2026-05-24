"""
Phase 2: Research Refine

Stress-tests the idea before any code is written.
Kills bad ideas early. Saves months of wasted work.

Steps:
1. Decompose into atomic claims
2. Literature stress test (find 3 closest papers, write kill argument)
3. Feasibility assessment (data, compute, baselines, timeline, risks)
4. Cross-model review (auditor scores novelty/feasibility ≥6 to proceed)
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from ..core.models import Idea, IdeaStatus
from ..core.config import LabConfig
from ..providers.llm import LLMProvider
from ..providers.literature import LiteratureProvider


DECOMPOSE_PROMPT = """Decompose this research idea into atomic claims.

Idea:
Title: {title}
Phenomenon: {phenomenon}
Hypothesis: {hypothesis}
Proposed method: {proposed_method}

An atomic claim is a single falsifiable statement that can be tested independently.
Examples:
- "Phenomenon X exists in domain Y" (existence claim)
- "Method M improves metric K by at least Z%" (performance claim)
- "The improvement is due to component C, not confounders" (mechanism claim)
- "The method generalizes to domain D" (generalization claim)

Output JSON array of claims:
[{{"claim": "...", "type": "existence|performance|mechanism|generalization|theoretical", "testable_by": "how to test this"}}]
"""

LITERATURE_STRESS_TEST_PROMPT = """You are stress-testing a research idea against the literature.

Idea:
Title: {title}
Hypothesis: {hypothesis}
Proposed method: {proposed_method}

Closest papers found:
{papers}

For each of the 3 closest papers, write:
1. How close is it to this idea?
2. What does it do that this idea also does?
3. What is the key difference that makes this idea still novel?

Then write the overall literature verdict:
- Does this idea survive the literature stress test?
- What is the minimum novelty claim that survives?

Output JSON:
{{
  "closest_papers": [
    {{"title": "...", "similarity": "high|medium|low", "overlap": "...", "key_difference": "..."}}
  ],
  "literature_verdict": "survives|borderline|killed",
  "minimum_novelty_claim": "the smallest claim that is still novel",
  "recommended_framing": "how to frame this to maximize novelty"
}}
"""

FEASIBILITY_PROMPT = """Assess the feasibility of this research idea.

Idea:
Title: {title}
Hypothesis: {hypothesis}
Proposed method: {proposed_method}
Domain: {domain}

Assess:
1. Data: What datasets are needed? Are they publicly available?
2. Compute: What GPU resources are needed? How long will experiments take?
3. Baselines: What are the 8+ baselines needed? Are they reproducible?
4. Timeline: Realistic timeline for a 3-6 month project?
5. Risks: What are the top 3 risks that could kill this project?
6. Dependencies: What external tools/libraries are needed?

Output JSON:
{{
  "data_available": true/false,
  "data_sources": ["dataset 1", "dataset 2"],
  "compute_estimate_gpu_hours": N,
  "baselines": ["baseline 1", ..., "baseline 8+"],
  "timeline_months": N,
  "top_risks": ["risk 1", "risk 2", "risk 3"],
  "dependencies": ["tool 1", "tool 2"],
  "feasibility_score": 0-10,
  "blocking_issues": ["issue 1"] or []
}}
"""


class ResearchRefine:
    def __init__(self, config: LabConfig, llm: LLMProvider, lit: LiteratureProvider):
        self.config = config
        self.llm = llm
        self.lit = lit

    async def run(self, idea: Idea) -> tuple[Idea, bool]:
        """
        Run research-refine on an idea.
        Returns (updated_idea, passed).
        Writes outputs to idea.workspace_dir.
        """
        workspace = Path(idea.workspace_dir) if (idea.workspace_dir and idea.workspace_dir.strip()) else None
        if workspace:
            workspace.mkdir(parents=True, exist_ok=True)

        # Step 1: Decompose into atomic claims
        claims = await self._decompose(idea)
        if workspace:
            (workspace / "ATOMIC_CLAIMS.md").write_text(
                "# Atomic Claims\n\n" + "\n".join(f"- {c['claim']}" for c in claims),
                encoding="utf-8",
            )

        # Step 2: Literature stress test
        papers = await self.lit.search_multi([
            f"{idea.domain} {idea.hypothesis[:80]}",
            f"{idea.proposed_method[:60]} {idea.domain}",
        ], limit_each=8)
        paper_text = self.lit.format_for_prompt(papers, max_papers=6)

        lit_response = await self.llm.complete(
            self.config.auditor(),
            [{"role": "user", "content": LITERATURE_STRESS_TEST_PROMPT.format(
                title=idea.title,
                hypothesis=idea.hypothesis,
                proposed_method=idea.proposed_method,
                papers=paper_text,
            )}],
            temperature=0.3,
            max_tokens=2048,
        )
        lit_result = self._parse_json(lit_response)
        lit_verdict = lit_result.get("literature_verdict", "killed")

        if workspace:
            (workspace / "LITERATURE_STRESS_TEST.md").write_text(
                f"# Literature Stress Test\n\n"
                f"**Verdict**: {lit_verdict}\n\n"
                f"**Minimum novelty claim**: {lit_result.get('minimum_novelty_claim', '')}\n\n"
                f"**Recommended framing**: {lit_result.get('recommended_framing', '')}\n\n"
                f"## Closest Papers\n\n"
                + "\n".join(
                    f"### {p.get('title', '')}\n"
                    f"- Similarity: {p.get('similarity', '')}\n"
                    f"- Overlap: {p.get('overlap', '')}\n"
                    f"- Key difference: {p.get('key_difference', '')}\n"
                    for p in lit_result.get("closest_papers", [])
                ),
                encoding="utf-8",
            )

        if lit_verdict == "killed":
            idea.status = IdeaStatus.KILLED
            return idea, False

        # Step 3: Feasibility assessment
        feasibility_response = await self.llm.complete(
            self.config.executor(),
            [{"role": "user", "content": FEASIBILITY_PROMPT.format(
                title=idea.title,
                hypothesis=idea.hypothesis,
                proposed_method=idea.proposed_method,
                domain=idea.domain,
            )}],
            temperature=0.3,
            max_tokens=2048,
        )
        feasibility = self._parse_json(feasibility_response)

        if workspace:
            (workspace / "FEASIBILITY.md").write_text(
                f"# Feasibility Assessment\n\n"
                f"**Score**: {feasibility.get('feasibility_score', 0)}/10\n"
                f"**Timeline**: {feasibility.get('timeline_months', '?')} months\n"
                f"**Compute**: {feasibility.get('compute_estimate_gpu_hours', '?')} GPU hours\n\n"
                f"## Data\n{', '.join(feasibility.get('data_sources', []))}\n\n"
                f"## Baselines\n" + "\n".join(f"- {b}" for b in feasibility.get("baselines", [])) + "\n\n"
                f"## Top Risks\n" + "\n".join(f"- {r}" for r in feasibility.get("top_risks", [])) + "\n\n"
                f"## Blocking Issues\n" + "\n".join(f"- {i}" for i in feasibility.get("blocking_issues", [])),
                encoding="utf-8",
            )

        feasibility_score = float(feasibility.get("feasibility_score", 0))
        blocking = feasibility.get("blocking_issues", [])

        if feasibility_score < self.config.min_feasibility_score or blocking:
            idea.status = IdeaStatus.KILLED
            return idea, False

        # Update idea with refined framing
        if lit_result.get("recommended_framing"):
            idea.metadata["recommended_framing"] = lit_result["recommended_framing"]
        if lit_result.get("minimum_novelty_claim"):
            idea.metadata["minimum_novelty_claim"] = lit_result["minimum_novelty_claim"]
        idea.metadata["baselines"] = feasibility.get("baselines", [])
        idea.metadata["data_sources"] = feasibility.get("data_sources", [])
        idea.metadata["timeline_months"] = feasibility.get("timeline_months", 6)
        idea.feasibility_score = feasibility_score
        idea.status = IdeaStatus.REFINED

        if workspace:
            (workspace / "RESEARCH_QUESTION.md").write_text(
                f"# Research Question\n\n"
                f"**Title**: {idea.title}\n\n"
                f"**Phenomenon**: {idea.phenomenon}\n\n"
                f"**Hypothesis**: {idea.hypothesis}\n\n"
                f"**Method**: {idea.proposed_method}\n\n"
                f"**Contribution**: {idea.expected_contribution}\n\n"
                f"**Novelty score**: {idea.novelty_score}/10\n"
                f"**Feasibility score**: {idea.feasibility_score}/10\n",
                encoding="utf-8",
            )

        return idea, True

    async def _decompose(self, idea: Idea) -> list[dict]:
        response = await self.llm.complete(
            self.config.executor(),
            [{"role": "user", "content": DECOMPOSE_PROMPT.format(
                title=idea.title,
                phenomenon=idea.phenomenon,
                hypothesis=idea.hypothesis,
                proposed_method=idea.proposed_method,
            )}],
            temperature=0.3,
            max_tokens=1024,
        )
        return self._parse_json_array(response)

    def _parse_json(self, text: str) -> dict:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            return {}

    def _parse_json_array(self, text: str) -> list[dict]:
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        try:
            result = json.loads(text.strip())
            return result if isinstance(result, list) else []
        except json.JSONDecodeError:
            return []
