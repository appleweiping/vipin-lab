"""
Anti-Toy Enforcement Engine.

The two failure modes of every auto-research system:

1. IDEA DEATH LOOP: LLM generates idea → self-checks → finds prior work →
   generates slightly different idea → finds prior work again → repeat forever.
   Solution: Divergence forcing. When an idea is killed by prior work, the system
   MUST pivot to a structurally different direction, not a surface variation.

2. TOY-IFICATION: System defaults to small datasets, weak baselines, toy metrics,
   or invents "environment constraints" to avoid hard experiments.
   Solution: Hardcoded minimum standards that cannot be overridden by LLM output.
   Any plan that violates these is rejected at the gate, not negotiated.

This engine enforces both.
"""
from __future__ import annotations
import re
from ..core.models import Idea, ExperimentPlan, ExperimentBlock
from ..core.config import LabConfig
from ..providers.llm import LLMProvider


# ── Toy detection thresholds (non-negotiable) ─────────────────────────────────

TOY_DATASET_PATTERNS = [
    r"\btoy\b", r"\bsynthetic\b", r"\bsimulated\b", r"\bsmall.scale\b",
    r"\b\d{1,3}\s*samples?\b",   # "50 samples", "100 samples"
    r"\bsubset\b.*\bfor\s+speed\b",
    r"\bfor\s+demonstration\b", r"\bproof.of.concept\b",
    r"\bpilot\s+study\b",
]

TOY_METRIC_PATTERNS = [
    r"\baccuracy\s+on\s+\d+\s+class\b",  # "accuracy on 2 class"
    r"\btoy\s+metric\b",
    r"\bsimplified\s+metric\b",
    r"\bproxy\s+metric\s+only\b",
]

ENVIRONMENT_EXCUSE_PATTERNS = [
    r"due\s+to\s+(?:compute|resource|environment)\s+constraints",
    r"limited\s+by\s+(?:compute|gpu|memory)",
    r"(?:cannot|can't|unable\s+to)\s+run\s+(?:full|complete|all)",
    r"(?:skip|omit|exclude)\s+(?:due\s+to|because\s+of)\s+(?:time|compute)",
    r"(?:smaller|reduced)\s+(?:version|scale)\s+(?:due\s+to|for)",
]

MINIMUM_STANDARDS = {
    "min_dataset_size": 1000,       # at least 1K samples
    "min_baselines": 8,             # at least 8 baselines
    "min_seeds": 20,                # at least 20 seeds for paper results
    "min_metrics": 3,               # at least 3 metrics reported
    "require_standard_benchmarks": True,  # must use established benchmarks
}


DIVERGENCE_PROMPT = """An idea was killed because it's too similar to prior work.
You must generate a STRUCTURALLY DIFFERENT direction — not a surface variation.

Domain: {domain}
Killed idea: {killed_idea}
Kill reason: {kill_reason}
Prior work that killed it: {prior_work}

FORBIDDEN: Any idea that is a variation of the killed idea (different model, different dataset,
different hyperparameter, different domain application of the same core method).

REQUIRED: A structurally different research direction that:
1. Addresses a DIFFERENT phenomenon than the killed idea
2. Uses a DIFFERENT theoretical framework
3. Cannot be described as "X but with Y changed"

Generate ONE structurally different direction. Explain WHY it's structurally different.

Output JSON:
{{
  "new_phenomenon": "a different anomaly/gap than the killed idea",
  "structural_difference": "why this is fundamentally different, not a variation",
  "new_hypothesis": "the falsifiable claim",
  "new_method": "the proposed approach",
  "why_not_variation": "explicit argument that this is not just X+Y stitching"
}}
"""

TOY_AUDIT_PROMPT = """You are auditing an experiment plan for toy-ification.

Toy-ification means: using small datasets, weak baselines, toy metrics, or inventing
"environment constraints" to avoid hard experiments. This is FORBIDDEN.

Experiment plan:
{plan_text}

Check for:
1. DATASET SIZE: Are datasets large enough? (minimum 1K samples, prefer standard benchmarks)
2. BASELINES: Are there ≥8 strong baselines? Are they the actual state-of-the-art?
3. METRICS: Are standard metrics used? (not simplified proxies)
4. ENVIRONMENT EXCUSES: Any "due to compute constraints" or "simplified for demonstration"?
5. SCALE: Is the experiment at publication-worthy scale?

For each violation, specify:
- What the violation is
- What the minimum acceptable standard is
- What must change

Output JSON:
{{
  "toy_violations": [
    {{"type": "dataset|baseline|metric|excuse|scale", "description": "...", "fix": "..."}}
  ],
  "is_toy": true/false,
  "severity": "critical|major|minor",
  "verdict": "pass|fail"
}}
"""


class AntiToyEngine:
    """
    Enforces minimum research standards and breaks idea generation death loops.
    """

    def __init__(self, config: LabConfig, llm: LLMProvider):
        self.config = config
        self.llm = llm
        self._killed_ideas: list[dict] = []  # track killed ideas to force divergence

    # ── Death loop prevention ─────────────────────────────────────────────────

    def record_killed_idea(self, idea: "Idea", kill_reason: str, prior_work: list[str]):
        """Record a killed idea to prevent surface-variation regeneration."""
        self._killed_ideas.append({
            "title": idea.title,
            "hypothesis": idea.hypothesis[:200],
            "method": idea.proposed_method[:200],
            "kill_reason": kill_reason,
            "prior_work": prior_work[:3],
        })

    def is_surface_variation(self, new_idea: "Idea") -> tuple[bool, str]:
        """
        Check if a new idea is a surface variation of a previously killed idea.
        Returns (is_variation, reason).
        """
        if not self._killed_ideas:
            return False, ""

        new_text = f"{new_idea.hypothesis} {new_idea.proposed_method}".lower()
        new_words = set(re.findall(r'\b\w{5,}\b', new_text))

        for killed in self._killed_ideas:
            killed_text = f"{killed['hypothesis']} {killed['method']}".lower()
            killed_words = set(re.findall(r'\b\w{5,}\b', killed_text))

            if not killed_words:
                continue

            overlap = len(new_words & killed_words) / len(killed_words)
            if overlap > 0.6:
                return True, (
                    f"Too similar to previously killed idea: '{killed['title']}' "
                    f"(word overlap: {overlap:.0%}). Must be structurally different."
                )

        return False, ""

    async def force_divergence(
        self,
        domain: str,
        killed_idea: "Idea",
        kill_reason: str,
        prior_work: list[str],
    ) -> dict | None:
        """
        When an idea is killed, force a structurally different direction.
        Returns new idea components or None if divergence fails.
        """
        import json, re as _re

        response = await self.llm.complete(
            self.config.architect(),
            [{"role": "user", "content": DIVERGENCE_PROMPT.format(
                domain=domain,
                killed_idea=f"{killed_idea.title}: {killed_idea.hypothesis[:150]}",
                kill_reason=kill_reason,
                prior_work=", ".join(prior_work[:3]),
            )}],
            temperature=0.8,  # higher temperature for divergence
            max_tokens=1024,
        )
        match = _re.search(r'\{.*\}', response, _re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None

    # ── Toy detection ─────────────────────────────────────────────────────────

    def check_plan_for_toys(self, plan: ExperimentPlan) -> tuple[bool, list[str]]:
        """
        Static check for toy-ification patterns in experiment plan.
        Returns (is_toy, violations).
        This runs BEFORE the LLM audit — catches obvious violations instantly.
        """
        violations = []

        for block in plan.blocks:
            # Check baseline count
            if len(block.baselines) < MINIMUM_STANDARDS["min_baselines"]:
                violations.append(
                    f"Block {block.id}: only {len(block.baselines)} baselines "
                    f"(minimum {MINIMUM_STANDARDS['min_baselines']})"
                )

            # Check seed count
            if block.seeds < MINIMUM_STANDARDS["min_seeds"]:
                violations.append(
                    f"Block {block.id}: only {block.seeds} seeds "
                    f"(minimum {MINIMUM_STANDARDS['min_seeds']} for paper results)"
                )

            # Check metric count
            all_metrics = block.primary_metrics + block.secondary_metrics
            if len(all_metrics) < MINIMUM_STANDARDS["min_metrics"]:
                violations.append(
                    f"Block {block.id}: only {len(all_metrics)} metrics "
                    f"(minimum {MINIMUM_STANDARDS['min_metrics']})"
                )

            # Check for toy patterns in hypothesis/expected_outcome
            text = f"{block.hypothesis} {block.expected_outcome}".lower()
            for pattern in TOY_DATASET_PATTERNS:
                if re.search(pattern, text):
                    violations.append(
                        f"Block {block.id}: toy dataset pattern detected: '{pattern}'"
                    )
                    break

            # Check for environment excuses
            for pattern in ENVIRONMENT_EXCUSE_PATTERNS:
                if re.search(pattern, text):
                    violations.append(
                        f"Block {block.id}: environment excuse detected — "
                        "experiments must run at full scale"
                    )
                    break

        return len(violations) > 0, violations

    async def audit_plan_for_toys(self, plan: ExperimentPlan) -> tuple[bool, list[str]]:
        """
        LLM-based toy audit. Runs after static check.
        Returns (is_toy, violations).
        """
        import json, re as _re

        plan_text = self._format_plan_for_audit(plan)
        response = await self.llm.complete(
            self.config.auditor(),
            [{"role": "user", "content": TOY_AUDIT_PROMPT.format(plan_text=plan_text)}],
            temperature=0.2,
            max_tokens=1024,
        )
        match = _re.search(r'\{.*\}', response, _re.DOTALL)
        if not match:
            return False, []
        try:
            result = json.loads(match.group())
        except json.JSONDecodeError:
            return False, []

        violations = [v["description"] for v in result.get("toy_violations", [])]
        is_toy = result.get("is_toy", False) or result.get("verdict") == "fail"
        return is_toy, violations

    def enforce_minimum_standards(self, plan: ExperimentPlan) -> ExperimentPlan:
        """
        Hard-enforce minimum standards on a plan.
        Raises ValueError if plan cannot be fixed automatically.
        """
        for block in plan.blocks:
            # Enforce minimum seeds
            if block.seeds < MINIMUM_STANDARDS["min_seeds"]:
                block.seeds = MINIMUM_STANDARDS["min_seeds"]

            # Enforce minimum metrics
            if len(block.primary_metrics) < 2:
                raise ValueError(
                    f"Block {block.id} has fewer than 2 primary metrics. "
                    "Cannot auto-fix — regenerate the experiment plan."
                )

        return plan

    def _format_plan_for_audit(self, plan: ExperimentPlan) -> str:
        lines = []
        for b in plan.blocks:
            lines.append(
                f"Block {b.id}: {b.name}\n"
                f"  Hypothesis: {b.hypothesis}\n"
                f"  Baselines ({len(b.baselines)}): {', '.join(b.baselines[:5])}\n"
                f"  Seeds: {b.seeds}\n"
                f"  Metrics: {', '.join(b.primary_metrics + b.secondary_metrics)}\n"
                f"  Expected: {b.expected_outcome[:100]}"
            )
        return "\n\n".join(lines)
