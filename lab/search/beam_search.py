"""
Beam Search for Idea Generation.

Inspired by AI Scientist v2's Best-First Tree Search (BFTS).
Explores multiple branches of idea space in parallel,
prunes weak branches early, expands promising ones.

Unlike BFTS which explores experiment code, this explores idea space:
- Root: phenomenon or seed input
- Branches: different hypotheses about the root cause
- Expansion: refine promising hypotheses into full ideas
- Pruning: kill-first score below threshold
"""
from __future__ import annotations
import asyncio
import json
import re
from dataclasses import dataclass, field
from ..core.models import Idea, Phenomenon
from ..core.config import LabConfig
from ..providers.llm import LLMProvider
from ..providers.literature import LiteratureProvider
# Import at module level to avoid hiding dependencies
from ..phases.p1_ideation import IdeaGenerator
from ..engines.kill_first import KillFirstEngine


@dataclass
class IdeaNode:
    hypothesis: str
    score: float = 0.0
    depth: int = 0
    parent_hypothesis: str = ""
    children: list["IdeaNode"] = field(default_factory=list)
    idea: Idea | None = None
    pruned: bool = False


HYPOTHESIS_GENERATION_PROMPT = """Generate {n} distinct hypotheses about the root cause of this phenomenon.

Domain: {domain}
Phenomenon: {phenomenon}
Prior context: {context}

Each hypothesis should:
1. Propose a different root cause (not just variations of the same idea)
2. Be falsifiable (can be tested with experiments)
3. Lead to a different method if true

Output JSON array:
[{{"hypothesis": "...", "root_cause": "...", "testable_by": "..."}}]
"""

HYPOTHESIS_SCORE_PROMPT = """Score these hypotheses for research potential.

Domain: {domain}
Phenomenon: {phenomenon}
Hypotheses:
{hypotheses}

For each, score 0-10 on:
- Novelty: how unexplored is this direction?
- Tractability: how feasible to test?
- Impact: if true, how much does it advance the field?

Output JSON array:
[{{"hypothesis": "...", "novelty": X, "tractability": X, "impact": X, "score": X}}]
"""


class IdeaBeamSearch:
    def __init__(
        self,
        config: LabConfig,
        llm: LLMProvider,
        lit: LiteratureProvider,
        beam_width: int = 4,
        max_depth: int = 2,
    ):
        self.config = config
        self.llm = llm
        self.lit = lit
        self.beam_width = beam_width
        self.max_depth = max_depth

    async def search(
        self,
        domain: str,
        phenomenon: Phenomenon,
        memory_context: str = "",
    ) -> list[Idea]:
        """
        Run beam search over hypothesis space.
        Returns top-k ideas after beam_width * max_depth exploration.
        """
        ideator = IdeaGenerator(self.config, self.llm, self.lit)
        kill_engine = KillFirstEngine(self.config, self.llm, self.lit)

        # Root: generate initial hypotheses
        root_hypotheses = await self._generate_hypotheses(
            domain, phenomenon.description, memory_context, n=self.beam_width * 2
        )
        if not root_hypotheses:
            return []

        # Score and select top beam_width
        scored = await self._score_hypotheses(domain, phenomenon.description, root_hypotheses)
        beam = scored[:self.beam_width]

        all_ideas = []

        for depth in range(self.max_depth):
            # Expand each node in beam into a full idea
            expand_tasks = []
            for node in beam:
                if not node.pruned:
                    expand_tasks.append(self._expand_node(
                        node, domain, phenomenon, ideator, kill_engine
                    ))

            results = await asyncio.gather(*expand_tasks)

            surviving_ideas = []
            next_beam_candidates = []

            for node, idea, survived in results:
                if idea:
                    all_ideas.append(idea)
                if survived and depth < self.max_depth - 1:
                    # Expand further: generate child hypotheses
                    children = await self._generate_hypotheses(
                        domain,
                        f"{phenomenon.description}\nBuilding on: {node.hypothesis}",
                        memory_context,
                        n=2,
                    )
                    for child_h in children:
                        child_node = IdeaNode(
                            hypothesis=child_h["hypothesis"],
                            depth=depth + 1,
                            parent_hypothesis=node.hypothesis,
                        )
                        next_beam_candidates.append(child_node)

            if next_beam_candidates:
                scored_children = await self._score_hypotheses(
                    domain, phenomenon.description,
                    [{"hypothesis": n.hypothesis} for n in next_beam_candidates]
                )
                beam = scored_children[:self.beam_width]
            else:
                break

        # Sort by novelty + feasibility
        all_ideas.sort(
            key=lambda i: i.novelty_score + i.feasibility_score,
            reverse=True,
        )
        return all_ideas[:self.beam_width]

    async def _expand_node(
        self,
        node: IdeaNode,
        domain: str,
        phenomenon: Phenomenon,
        ideator,
        kill_engine,
    ) -> tuple[IdeaNode, Idea | None, bool]:
        """Expand a hypothesis node into a full idea and run kill-first."""
        # Override phenomenon description with this specific hypothesis
        modified_phenomenon = Phenomenon(
            id=phenomenon.id,
            domain=domain,
            description=phenomenon.description,
            evidence=phenomenon.evidence,
            unexplained_by=phenomenon.unexplained_by,
            potential_causes=[node.hypothesis],
            severity=phenomenon.severity,
        )
        idea = await ideator.from_phenomenon(domain, modified_phenomenon)
        if not idea:
            node.pruned = True
            return node, None, False

        idea, survived = await kill_engine.evaluate(idea)
        if not survived:
            node.pruned = True

        node.idea = idea
        node.score = idea.novelty_score + idea.feasibility_score
        return node, idea, survived

    async def _generate_hypotheses(
        self, domain: str, phenomenon: str, context: str, n: int
    ) -> list[dict]:
        response = await self.llm.complete(
            self.config.architect(),
            [{"role": "user", "content": HYPOTHESIS_GENERATION_PROMPT.format(
                domain=domain, phenomenon=phenomenon[:300],
                context=context[:200] if context else "none", n=n,
            )}],
            temperature=0.7,
            max_tokens=1024,
        )
        return self._parse_json_array(response)

    async def _score_hypotheses(
        self, domain: str, phenomenon: str, hypotheses: list[dict]
    ) -> list[IdeaNode]:
        if not hypotheses:
            return []
        hyp_text = "\n".join(
            f"{i+1}. {h.get('hypothesis', '')}" for i, h in enumerate(hypotheses)
        )
        response = await self.llm.complete(
            self.config.auditor(),
            [{"role": "user", "content": HYPOTHESIS_SCORE_PROMPT.format(
                domain=domain, phenomenon=phenomenon[:200], hypotheses=hyp_text
            )}],
            temperature=0.2,
            max_tokens=1024,
        )
        scored = self._parse_json_array(response)

        nodes = []
        for i, h in enumerate(hypotheses):
            score_data = scored[i] if i < len(scored) else {}
            score = float(score_data.get("score", 5.0))
            nodes.append(IdeaNode(hypothesis=h.get("hypothesis", ""), score=score))

        nodes.sort(key=lambda n: n.score, reverse=True)
        return nodes

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
