"""
Evidence Gate Engine.

Enforces ARIS evidence discipline throughout the pipeline.
Every result gets labeled. Only paper_result evidence goes in the paper.

Evidence labels (from ARIS):
- paper_result: 20+ seeds, statistically valid, fair comparison → main paper
- official: full seeds, needs one more check → almost
- diagnostic: partial seeds / preliminary → supplementary only
- pilot: quick test → never in paper

This engine:
1. Validates experiment results against evidence criteria
2. Labels each result with the appropriate evidence level
3. Blocks paper claims that lack paper_result evidence
4. Generates the claim-evidence map
"""
from __future__ import annotations
import json
import re
from ..core.models import (
    ExperimentBlock, ExperimentPlan, Claim, EvidenceLabel, Paper
)
from ..core.config import LabConfig
from ..providers.llm import LLMProvider


EVIDENCE_AUDIT_PROMPT = """You are auditing experiment results for evidence quality.
This is a strict audit — you are a different agent from the one who ran the experiments.

Experiment block: {block_name}
Hypothesis: {hypothesis}
Results: {results}
Seeds used: {seeds}
Baselines compared: {baselines}
Metrics reported: {metrics}

Evidence criteria:
- paper_result: ≥20 seeds, paired t-test p<0.05, effect size reported, ≥8 baselines, same data splits
- official: ≥20 seeds, statistically valid, but needs one more verification
- diagnostic: 3-19 seeds OR missing statistical test OR <8 baselines
- pilot: <3 seeds OR no statistical test OR single baseline

Fairness check:
- Same data splits as baselines? (required for paper_result)
- Same preprocessing? (required for paper_result)
- Same compute budget? (required for paper_result)
- Hyperparameter tuning fair? (required for paper_result)

Output JSON:
{{
  "evidence_label": "paper_result|official|diagnostic|pilot",
  "seeds_count": N,
  "statistical_test": "t-test|none|other",
  "p_value": X or null,
  "effect_size": X or null,
  "baselines_count": N,
  "fairness_issues": ["issue 1"] or [],
  "reasoning": "why this label",
  "can_use_in_paper": true/false
}}
"""

CLAIM_EXTRACTION_PROMPT = """Extract all claims from this paper section and map them to evidence.

Section: {section_name}
Content: {content}

For each claim, identify:
1. The exact claim text
2. What type: empirical (numbers), novelty (first/new), theoretical (proof)
3. What evidence is needed to support it
4. Whether the evidence exists in the experiment results

Output JSON array:
[{{
  "claim_text": "...",
  "claim_type": "empirical|novelty|theoretical",
  "evidence_needed": "what experiment/result supports this",
  "evidence_exists": true/false,
  "evidence_label": "paper_result|official|diagnostic|pilot|none",
  "overclaim_risk": "high|medium|low",
  "overclaim_reason": "why it might be overclaiming" or null
}}]
"""


class EvidenceGate:
    def __init__(self, config: LabConfig, llm: LLMProvider):
        self.config = config
        self.llm = llm

    async def audit_block(self, block: ExperimentBlock) -> ExperimentBlock:
        """Audit a single experiment block and assign evidence label."""
        if not block.results:
            block.evidence_label = EvidenceLabel.PILOT
            return block

        audit_response = await self.llm.complete(
            self.config.auditor(),
            [{"role": "user", "content": EVIDENCE_AUDIT_PROMPT.format(
                block_name=block.name,
                hypothesis=block.hypothesis,
                results=json.dumps(block.results, indent=2)[:2000],
                seeds=block.seeds,
                baselines=", ".join(block.baselines),
                metrics=", ".join(block.primary_metrics),
            )}],
            temperature=0.1,
            max_tokens=1024,
        )
        audit = self._parse_json(audit_response)
        if not audit:
            block.evidence_label = EvidenceLabel.PILOT
            return block

        label_str = audit.get("evidence_label", "pilot")
        try:
            block.evidence_label = EvidenceLabel(label_str)
        except ValueError:
            block.evidence_label = EvidenceLabel.PILOT

        # Store audit results in block metadata
        block.results["_evidence_audit"] = audit
        return block

    async def audit_plan(self, plan: ExperimentPlan) -> dict[str, float]:
        """
        Audit the full experiment plan before running.
        Returns scores: Evidence, Rigor, Gates, Feasibility, Paper-potential.
        All must be ≥6 to proceed (ARIS rule).
        """
        plan_text = self._format_plan(plan)

        audit_prompt = f"""You are auditing an experiment plan before execution.
Score each dimension 0-10. All must be ≥6 to proceed.

Experiment plan:
{plan_text}

Scoring criteria:
- Evidence (0-10): Are the evidence requirements clear? Will results be paper_result quality?
- Rigor (0-10): Are there ≥8 baselines? ≥20 seeds planned? Statistical tests specified?
- Gates (0-10): Are there concrete kill conditions? Clear pass/fail thresholds?
- Feasibility (0-10): Can this be done in the estimated time with standard resources?
- Paper-potential (0-10): If results are positive, is this publishable at a top venue?

Output JSON:
{{
  "Evidence": X,
  "Rigor": X,
  "Gates": X,
  "Feasibility": X,
  "Paper-potential": X,
  "blocking_issues": ["issue 1"] or [],
  "verdict": "approved|needs_revision|rejected"
}}"""

        response = await self.llm.complete(
            self.config.auditor(),
            [{"role": "user", "content": audit_prompt}],
            temperature=0.2,
            max_tokens=1024,
        )
        scores = self._parse_json(response)
        # Default to failing scores if parse fails — never approve on empty response
        _DIMS = ("Evidence", "Rigor", "Gates", "Feasibility", "Paper-potential")
        if not scores:
            plan.audit_scores = {d: 0.0 for d in _DIMS}
            plan.approved = False
            return plan.audit_scores

        plan.audit_scores = {
            k: float(v) for k, v in scores.items()
            if k in _DIMS
        }
        # Require BOTH LLM verdict AND all scores ≥ threshold
        llm_approved = scores.get("verdict") == "approved"
        scores_pass = bool(plan.audit_scores) and all(
            v >= self.config.min_experiment_audit_score
            for v in plan.audit_scores.values()
        )
        plan.approved = llm_approved and scores_pass
        return plan.audit_scores

    async def extract_claims(self, paper: Paper) -> list[Claim]:
        """Extract and validate all claims in a paper."""
        claims = []
        for section_name, content in paper.sections.items():
            if not content:
                continue
            response = await self.llm.complete(
                self.config.auditor(),
                [{"role": "user", "content": CLAIM_EXTRACTION_PROMPT.format(
                    section_name=section_name,
                    content=content[:3000],
                )}],
                temperature=0.2,
                max_tokens=2048,
            )
            raw_claims = self._parse_json_array(response)
            for rc in raw_claims:
                label_str = rc.get("evidence_label", "none")
                try:
                    label = EvidenceLabel(label_str)
                except ValueError:
                    label = EvidenceLabel.PILOT

                claims.append(Claim(
                    text=rc.get("claim_text", ""),
                    claim_type=rc.get("claim_type", "empirical"),
                    evidence_ids=[],
                    evidence_label=label,
                    verified=rc.get("evidence_exists", False) and label == EvidenceLabel.PAPER_RESULT,
                ))
        paper.claims = claims
        return claims

    def check_paper_ready(self, paper: Paper) -> tuple[bool, list[str]]:
        """Check if all claims have paper_result evidence. Returns (ready, issues)."""
        issues = []
        for claim in paper.claims:
            if claim.claim_type == "empirical" and not claim.verified:
                issues.append(f"Unverified empirical claim: {claim.text[:100]}")
            if claim.claim_type == "empirical" and claim.evidence_label not in (
                EvidenceLabel.PAPER_RESULT, EvidenceLabel.OFFICIAL
            ):
                issues.append(
                    f"Claim uses {claim.evidence_label.value} evidence (need paper_result): "
                    f"{claim.text[:80]}"
                )
        return len(issues) == 0, issues

    def _format_plan(self, plan: ExperimentPlan) -> str:
        lines = [f"Idea: {plan.idea_id}", f"Blocks: {len(plan.blocks)}"]
        for b in plan.blocks:
            lines.append(
                f"\nBlock {b.id}: {b.name}\n"
                f"  Hypothesis: {b.hypothesis}\n"
                f"  Baselines: {len(b.baselines)} ({', '.join(b.baselines[:3])}...)\n"
                f"  Seeds: {b.seeds}\n"
                f"  Kill condition: {b.kill_condition}"
            )
        lines.append(f"\nMilestone gates: {'; '.join(plan.milestone_gates)}")
        lines.append(f"Fairness constraints: {'; '.join(plan.fairness_constraints)}")
        return "\n".join(lines)

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
