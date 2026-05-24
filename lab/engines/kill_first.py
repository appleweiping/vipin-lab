"""
Kill-First Ideation Engine.

The most important engine. Every idea must survive adversarial review
before it proceeds. We write the strongest possible objection first.

This is the opposite of how most auto-research systems work.
They generate ideas and then try to validate them.
We generate ideas and immediately try to kill them.

An idea that survives 3 rounds of kill arguments is worth pursuing.
An idea that dies in round 1 saved us months of wasted work.

Kill argument types:
1. Prior work kill: "Paper X already does exactly this"
2. Theoretical kill: "This can't work because of Y"
3. Empirical kill: "This was tried in Z and failed because..."
4. Scope kill: "This only works under assumption A which doesn't hold in practice"
5. Novelty kill: "This is just A + B stitching, not a genuine contribution"
"""
from __future__ import annotations
import json
import re
from ..core.models import Idea, KillArgument
from ..core.config import LabConfig
from ..providers.llm import LLMProvider
from ..providers.literature import LiteratureProvider


KILL_ARGUMENT_PROMPT = """You are a hostile reviewer at a top ML venue (NeurIPS/ICML/ICLR).
Your job is to write the STRONGEST POSSIBLE rejection argument for this idea.

Idea:
Title: {title}
Phenomenon: {phenomenon}
Hypothesis: {hypothesis}
Proposed method: {proposed_method}
Expected contribution: {expected_contribution}

Closest prior work found:
{prior_work}

Write the kill argument. Be specific, cite papers, be brutal.
Types of kill arguments to consider:
1. Prior work kill: does this already exist?
2. Theoretical kill: why can't this work?
3. Empirical kill: was this tried and failed?
4. Scope kill: does this only work under unrealistic assumptions?
5. Novelty kill: is this just A+B stitching?

Output JSON:
{{
  "kill_type": "prior_work|theoretical|empirical|scope|novelty|multiple",
  "argument": "the strongest rejection argument in 2-3 paragraphs",
  "closest_prior_work": ["paper 1", "paper 2"],
  "fatal_flaw": "the single most damaging point",
  "confidence_this_kills_idea": 0.0-1.0
}}
"""

REBUTTAL_PROMPT = """You are the author of this research idea. A hostile reviewer has written a kill argument.
Write the strongest possible rebuttal.

Idea:
Title: {title}
Phenomenon: {phenomenon}
Hypothesis: {hypothesis}
Proposed method: {proposed_method}

Kill argument:
{kill_argument}

Write a rebuttal that:
1. Directly addresses the fatal flaw
2. Explains why the prior work doesn't actually kill this idea (if applicable)
3. Clarifies what makes this genuinely novel
4. Acknowledges any valid points and explains how they're addressed

Output JSON:
{{
  "rebuttal": "the rebuttal in 2-3 paragraphs",
  "valid_points_acknowledged": ["point 1"],
  "key_differentiators": ["what makes this different from prior work"],
  "idea_survives": true/false,
  "confidence": 0.0-1.0
}}
"""

NOVELTY_SCORE_PROMPT = """You are scoring a research idea for novelty and feasibility.

Idea:
Title: {title}
Phenomenon: {phenomenon}
Hypothesis: {hypothesis}
Proposed method: {proposed_method}
Kill argument: {kill_argument}
Rebuttal: {rebuttal}

Score on:
1. Novelty (0-10): Is this genuinely new? Not just A+B stitching?
   - 9-10: Completely new problem formulation or method class
   - 7-8: New application of existing method with non-trivial adaptation
   - 5-6: Incremental improvement with clear contribution
   - 3-4: Minor variation of existing work
   - 1-2: Essentially already done

2. Feasibility (0-10): Can this be done in 3-6 months with standard resources?
   - 9-10: Clear path, standard tools, well-defined experiments
   - 7-8: Some challenges but tractable
   - 5-6: Significant challenges, may need to simplify
   - 3-4: Major obstacles, high risk
   - 1-2: Likely infeasible

3. Impact (0-10): If it works, how much does it advance the field?

Output JSON:
{{
  "novelty_score": X,
  "feasibility_score": X,
  "impact_score": X,
  "novelty_reasoning": "...",
  "feasibility_reasoning": "...",
  "recommendation": "proceed|iterate|kill"
}}
"""


class KillFirstEngine:
    def __init__(self, config: LabConfig, llm: LLMProvider, lit: LiteratureProvider):
        self.config = config
        self.llm = llm
        self.lit = lit

    async def evaluate(self, idea: Idea) -> tuple[Idea, bool]:
        """
        Run kill-first evaluation on an idea.
        Returns (updated_idea, survived).
        """
        # Find closest prior work
        prior_papers = await self.lit.search_multi([
            f"{idea.domain} {idea.hypothesis[:100]}",
            f"{idea.proposed_method[:80]} {idea.domain}",
            f"{idea.phenomenon[:80]} solution method",
        ], limit_each=5)
        prior_text = self.lit.format_for_prompt(prior_papers, max_papers=8)

        # Round 1: Write kill argument (using auditor — different from idea generator)
        kill_response = await self.llm.complete(
            self.config.auditor(),
            [{"role": "user", "content": KILL_ARGUMENT_PROMPT.format(
                title=idea.title,
                phenomenon=idea.phenomenon,
                hypothesis=idea.hypothesis,
                proposed_method=idea.proposed_method,
                expected_contribution=idea.expected_contribution,
                prior_work=prior_text,
            )}],
            temperature=0.3,
            max_tokens=2048,
        )
        kill_data = self._parse_json(kill_response)
        if not kill_data:
            return idea, False

        kill_confidence = float(kill_data.get("confidence_this_kills_idea", 0.5))

        # Round 2: Write rebuttal (using architect — the "author")
        rebuttal_response = await self.llm.complete(
            self.config.architect(),
            [{"role": "user", "content": REBUTTAL_PROMPT.format(
                title=idea.title,
                phenomenon=idea.phenomenon,
                hypothesis=idea.hypothesis,
                proposed_method=idea.proposed_method,
                kill_argument=kill_data.get("argument", ""),
            )}],
            temperature=0.4,
            max_tokens=2048,
        )
        rebuttal_data = self._parse_json(rebuttal_response)
        if not rebuttal_data:
            return idea, False

        idea_survives = rebuttal_data.get("idea_survives", False)
        rebuttal_confidence = float(rebuttal_data.get("confidence", 0.5))

        # Round 3: Score novelty and feasibility
        score_response = await self.llm.complete(
            self.config.auditor(),
            [{"role": "user", "content": NOVELTY_SCORE_PROMPT.format(
                title=idea.title,
                phenomenon=idea.phenomenon,
                hypothesis=idea.hypothesis,
                proposed_method=idea.proposed_method,
                kill_argument=kill_data.get("argument", ""),
                rebuttal=rebuttal_data.get("rebuttal", ""),
            )}],
            temperature=0.2,
            max_tokens=1024,
        )
        scores = self._parse_json(score_response)

        # Update idea
        idea.novelty_score = float(scores.get("novelty_score", 0))
        idea.feasibility_score = float(scores.get("feasibility_score", 0))
        idea.kill_argument = KillArgument(
            argument=kill_data.get("argument", ""),
            closest_prior_work=kill_data.get("closest_prior_work", []),
            rebuttal=rebuttal_data.get("rebuttal", ""),
            survived=idea_survives and idea.is_viable(),
            reviewer_model=self.config.auditor().id,
        )

        recommendation = scores.get("recommendation", "kill")
        survived = (
            recommendation == "proceed"
            and idea.is_viable()
            and idea_survives
        )

        return idea, survived

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
