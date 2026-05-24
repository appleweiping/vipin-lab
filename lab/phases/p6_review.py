"""
Phase 6: Auto Review Loop

Multi-agent peer review. Different agents from the paper writer.
Codex as Reviewer 1 (structured rubric).
Codex as Adversary (kill argument).
Sonnet as Reviewer 2 (quick scan).
Max 3 iterations. All scores must be ≥7 to pass.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from ..core.models import Idea, Paper
from ..core.config import LabConfig
from ..providers.llm import LLMProvider


REVIEWER_1_PROMPT = """You are Reviewer 1 at a top ML venue (NeurIPS/ICML/ICLR).
Score this paper on each dimension 1-10. Be rigorous and honest.

Paper title: {title}
Abstract: {abstract}
Introduction: {introduction}
Method: {method}
Results: {results}

Scoring rubric:
- Novelty (1-10): Is the contribution genuinely new? Not just A+B stitching?
- Clarity (1-10): Is the paper well-written and easy to follow?
- Soundness (1-10): Are the experiments rigorous? Statistical tests? Fair comparison?
- Significance (1-10): Does this advance the field meaningfully?
- Reproducibility (1-10): Can others reproduce this? Are configs/code described?
- Completeness (1-10): Are all necessary experiments included? Ablations?
- Presentation (1-10): Figures, tables, writing quality?

For each score below 7, write a specific actionable fix.

Output JSON:
{{
  "scores": {{
    "Novelty": X, "Clarity": X, "Soundness": X, "Significance": X,
    "Reproducibility": X, "Completeness": X, "Presentation": X
  }},
  "overall_score": X,
  "recommendation": "accept|weak_accept|weak_reject|reject",
  "major_weaknesses": ["weakness 1", "weakness 2"],
  "minor_weaknesses": ["weakness 3"],
  "actionable_fixes": {{"Soundness": "add paired t-tests", ...}},
  "questions_for_authors": ["question 1", "question 2"]
}}
"""

ADVERSARY_PROMPT = """You are writing the strongest possible rejection argument for this paper.
Your goal is to find the fatal flaw that would cause rejection at a top venue.

Paper title: {title}
Abstract: {abstract}
Method: {method}
Results: {results}

Write the kill argument. Types to consider:
1. The main result is not statistically significant
2. The comparison is unfair (different data, preprocessing, compute)
3. The method is not novel (prior work X already does this)
4. The ablation is missing (we don't know what drives the improvement)
5. The improvement is marginal and within noise
6. The method only works under unrealistic assumptions

Output JSON:
{{
  "fatal_flaw": "the single most damaging point",
  "kill_argument": "2-3 paragraph rejection argument",
  "confidence_this_kills_paper": 0.0-1.0,
  "fixable": true/false,
  "fix_required": "what would need to change to address this"
}}
"""

AUTHOR_RESPONSE_PROMPT = """You are the author responding to peer review.

Paper: {title}
Review scores: {scores}
Major weaknesses: {weaknesses}
Adversary kill argument: {kill_argument}

Write a response that:
1. Addresses each major weakness with a concrete fix
2. Rebuts the kill argument
3. Classifies each weakness: fatal (must fix) / major (should fix) / minor (can address)
4. Proposes specific changes to the paper

Output JSON:
{{
  "weakness_classification": [
    {{"weakness": "...", "severity": "fatal|major|minor", "fix": "..."}}
  ],
  "kill_argument_rebuttal": "...",
  "revision_plan": ["change 1", "change 2", "change 3"],
  "paper_survives": true/false
}}
"""


class AutoReviewLoop:
    def __init__(self, config: LabConfig, llm: LLMProvider):
        self.config = config
        self.llm = llm

    async def run(self, idea: Idea, paper: Paper) -> tuple[Paper, bool]:
        """Run auto-review loop. Returns (updated_paper, passed)."""
        workspace = Path(idea.workspace_dir) if idea.workspace_dir else None
        review_log = []

        for iteration in range(self.config.max_review_iterations):
            # Reviewer 1 (auditor model — different from paper writer)
            r1_response = await self.llm.complete(
                self.config.auditor(),
                [{"role": "user", "content": REVIEWER_1_PROMPT.format(
                    title=paper.title,
                    abstract=paper.abstract[:500],
                    introduction=paper.sections.get("introduction", "")[:1000],
                    method=paper.sections.get("method", "")[:1000],
                    results=paper.sections.get("results", "")[:1000],
                )}],
                temperature=0.3,
                max_tokens=2048,
            )
            r1 = self._parse_json(r1_response)

            # Adversary (architect model — strongest objector)
            adv_response = await self.llm.complete(
                self.config.architect(),
                [{"role": "user", "content": ADVERSARY_PROMPT.format(
                    title=paper.title,
                    abstract=paper.abstract[:500],
                    method=paper.sections.get("method", "")[:1000],
                    results=paper.sections.get("results", "")[:1000],
                )}],
                temperature=0.3,
                max_tokens=1024,
            )
            adv = self._parse_json(adv_response)

            scores = r1.get("scores", {})
            overall = float(r1.get("overall_score", 5))
            all_pass = all(v >= self.config.min_review_score for v in scores.values())

            review_log.append({
                "iteration": iteration + 1,
                "scores": scores,
                "overall": overall,
                "recommendation": r1.get("recommendation", "reject"),
                "fatal_flaw": adv.get("fatal_flaw", ""),
                "kill_confidence": adv.get("confidence_this_kills_paper", 0),
            })

            if all_pass and adv.get("confidence_this_kills_paper", 1) < 0.4:
                paper.review_scores = scores
                break

            # Author response and revision
            author_response = await self.llm.complete(
                self.config.executor(),
                [{"role": "user", "content": AUTHOR_RESPONSE_PROMPT.format(
                    title=paper.title,
                    scores=json.dumps(scores),
                    weaknesses=json.dumps(r1.get("major_weaknesses", [])),
                    kill_argument=adv.get("kill_argument", ""),
                )}],
                temperature=0.4,
                max_tokens=2048,
            )
            author = self._parse_json(author_response)

            if not author.get("paper_survives", True):
                break

            # Apply fixes to paper sections
            await self._apply_fixes(paper, author.get("revision_plan", []), idea)

        # Write review log
        if workspace:
            papers_dir = workspace / "papers"
            papers_dir.mkdir(exist_ok=True)
            log_lines = ["# Review Log\n"]
            for entry in review_log:
                log_lines.append(f"## Iteration {entry['iteration']}\n")
                log_lines.append(f"**Overall**: {entry['overall']}/10 — {entry['recommendation']}\n")
                log_lines.append("**Scores**:\n")
                for dim, score in entry.get("scores", {}).items():
                    status = "✓" if score >= self.config.min_review_score else "✗"
                    log_lines.append(f"- {dim}: {score}/10 {status}")
                log_lines.append(f"\n**Fatal flaw**: {entry.get('fatal_flaw', 'none')}\n")
            (papers_dir / "REVIEW_LOG.md").write_text("\n".join(log_lines), encoding="utf-8")

        final_scores = paper.review_scores
        passed = (
            bool(final_scores)
            and all(v >= self.config.min_review_score for v in final_scores.values())
        )
        return paper, passed

    async def _apply_fixes(self, paper: Paper, revision_plan: list[str], idea: Idea):
        """Apply revision plan to paper sections."""
        if not revision_plan:
            return
        # For each fix, ask the executor to revise the relevant section
        for fix in revision_plan[:3]:  # limit to top 3 fixes per iteration
            section = self._identify_section(fix)
            if section and section in paper.sections:
                response = await self.llm.complete(
                    self.config.executor(),
                    [{"role": "user", "content":
                        f"Revise this paper section to address the following fix:\n\n"
                        f"Fix: {fix}\n\n"
                        f"Current section ({section}):\n{paper.sections[section][:2000]}\n\n"
                        f"Write the revised section. Keep the same structure but address the fix."}],
                    temperature=0.4,
                    max_tokens=2000,
                )
                paper.sections[section] = response.strip()

    def _identify_section(self, fix: str) -> str | None:
        fix_lower = fix.lower()
        if any(w in fix_lower for w in ["experiment", "baseline", "statistical", "result", "metric"]):
            return "experiments"
        if any(w in fix_lower for w in ["method", "model", "algorithm", "approach"]):
            return "method"
        if any(w in fix_lower for w in ["introduction", "motivation", "problem"]):
            return "introduction"
        if any(w in fix_lower for w in ["related", "prior", "literature"]):
            return "related_work"
        return None

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
