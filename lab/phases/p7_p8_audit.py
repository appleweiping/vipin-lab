"""
Phase 7: Citation Audit
Phase 8: Paper Claim Audit

Two final gates before the paper is marked ready.
Both done by a different agent than the paper writer.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from ..core.models import Idea, Paper, IdeaStatus
from ..core.config import LabConfig
from ..providers.llm import LLMProvider
from ..providers.literature import LiteratureProvider


CITATION_AUDIT_PROMPT = """You are auditing the citations in a research paper.

Paper title: {title}
Domain: {domain}
Citations listed: {citations}
Related work section: {related_work}

Check:
1. Completeness: Are seminal papers in this domain cited? Recent papers (2024-2025)?
2. Fairness: Are the 3 closest competitors cited? Are their strengths acknowledged?
3. Breadth: Are papers from different sub-areas cited?
4. Technical accuracy: Are papers cited for the right claims?

Minimum for top venue: {min_citations} citations.

Output JSON:
{{
  "citation_count": N,
  "missing_seminal": ["paper 1", "paper 2"],
  "missing_recent": ["paper 3"],
  "missing_competitors": ["paper 4"],
  "fairness_issues": ["issue 1"],
  "verdict": "pass|needs_additions|fail",
  "additions_required": ["add paper X for claim Y"]
}}
"""

CLAIM_AUDIT_PROMPT = """You are auditing all claims in a research paper.
This is the final gate before submission. Be thorough and strict.

Paper title: {title}
Abstract: {abstract}
All sections: {sections_summary}
Evidence available: {evidence_summary}

For each type of claim, check:

EMPIRICAL CLAIMS (numbers, comparisons):
- Does the number match the experiment results?
- Is the comparison fair (same data, preprocessing, compute)?
- Is statistical significance reported?
- Are seeds ≥20?

NOVELTY CLAIMS ("first", "new", "novel", "state-of-the-art"):
- Is there literature evidence that no prior work does exactly this?
- Is "state-of-the-art" backed by comparison to all recent methods?

THEORETICAL CLAIMS (proofs, guarantees):
- Is the proof complete?
- Are assumptions stated?
- Are edge cases addressed?

OVERCLAIM DETECTION:
- "significantly better" without numbers → flag
- "state-of-the-art" without comparison → flag
- "first ever" without literature search → flag
- "always works" without robustness analysis → flag

Output JSON:
{{
  "empirical_issues": ["issue 1"],
  "novelty_issues": ["issue 2"],
  "theoretical_issues": ["issue 3"],
  "overclaims": ["overclaim 1"],
  "consistency_issues": ["abstract says X but results show Y"],
  "verdict": "ready|needs_revision|not_ready",
  "blocking_issues": ["issue that must be fixed before submission"]
}}
"""


class CitationAudit:
    def __init__(self, config: LabConfig, llm: LLMProvider, lit: LiteratureProvider):
        self.config = config
        self.llm = llm
        self.lit = lit

    async def run(self, idea: Idea, paper: Paper) -> tuple[bool, list[str]]:
        """Audit citations. Returns (passed, issues)."""
        response = await self.llm.complete(
            self.config.auditor(),
            [{"role": "user", "content": CITATION_AUDIT_PROMPT.format(
                title=paper.title,
                domain=idea.domain,
                citations=", ".join(paper.citations[:30]),
                related_work=paper.sections.get("related_work", "")[:2000],
                min_citations=self.config.min_citations,
            )}],
            temperature=0.2,
            max_tokens=1024,
        )
        result = self._parse_json(response)
        verdict = result.get("verdict", "fail")
        issues = (
            result.get("missing_seminal", [])
            + result.get("missing_competitors", [])
            + result.get("fairness_issues", [])
        )

        workspace = Path(idea.workspace_dir) if idea.workspace_dir else None
        if workspace:
            papers_dir = workspace / "papers"
            papers_dir.mkdir(exist_ok=True)
            (papers_dir / "CITATION_AUDIT.md").write_text(
                f"# Citation Audit\n\n**Verdict**: {verdict}\n\n"
                f"**Count**: {result.get('citation_count', len(paper.citations))}\n\n"
                f"## Issues\n" + "\n".join(f"- {i}" for i in issues) + "\n\n"
                f"## Additions Required\n"
                + "\n".join(f"- {a}" for a in result.get("additions_required", [])),
                encoding="utf-8",
            )

        return verdict == "pass", issues

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


class PaperClaimAudit:
    def __init__(self, config: LabConfig, llm: LLMProvider):
        self.config = config
        self.llm = llm

    async def run(self, idea: Idea, paper: Paper) -> tuple[bool, list[str]]:
        """Final claim audit. Returns (passed, blocking_issues)."""
        sections_summary = "\n\n".join(
            f"[{k}]: {v[:500]}" for k, v in paper.sections.items()
        )
        evidence_summary = "\n".join(
            f"- {c.text[:80]}: {c.evidence_label.value} ({'verified' if c.verified else 'unverified'})"
            for c in paper.claims[:20]
        )

        response = await self.llm.complete(
            self.config.auditor(),
            [{"role": "user", "content": CLAIM_AUDIT_PROMPT.format(
                title=paper.title,
                abstract=paper.abstract[:500],
                sections_summary=sections_summary[:3000],
                evidence_summary=evidence_summary or "No claims extracted yet",
            )}],
            temperature=0.2,
            max_tokens=2048,
        )
        result = self._parse_json(response)
        verdict = result.get("verdict", "not_ready")
        blocking = result.get("blocking_issues", [])

        workspace = Path(idea.workspace_dir) if idea.workspace_dir else None
        if workspace:
            papers_dir = workspace / "papers"
            papers_dir.mkdir(exist_ok=True)
            (papers_dir / "CLAIM_AUDIT.md").write_text(
                f"# Claim Audit\n\n**Verdict**: {verdict}\n\n"
                f"## Blocking Issues\n" + "\n".join(f"- {i}" for i in blocking) + "\n\n"
                f"## Empirical Issues\n" + "\n".join(f"- {i}" for i in result.get("empirical_issues", [])) + "\n\n"
                f"## Overclaims\n" + "\n".join(f"- {i}" for i in result.get("overclaims", [])) + "\n\n"
                f"## Consistency Issues\n" + "\n".join(f"- {i}" for i in result.get("consistency_issues", [])),
                encoding="utf-8",
            )

        paper.claim_audit_passed = verdict == "ready"
        if verdict == "ready":
            idea.status = IdeaStatus.READY

        return verdict == "ready", blocking

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
