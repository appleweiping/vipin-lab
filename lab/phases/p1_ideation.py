"""
Phase 1: Idea Generation

Three modes:
1. phenomenon_driven — start from observed anomaly, derive hypothesis
2. extension — extend an existing project with follow-up directions
3. transfer — apply cross-domain analogy to generate new idea

All modes produce Idea objects that go through kill-first evaluation.
"""
from __future__ import annotations
import json
import re
import uuid
from ..core.models import Idea, IdeaOrigin, Phenomenon, DomainAnalogy
from ..core.config import LabConfig
from ..providers.llm import LLMProvider
from ..providers.literature import LiteratureProvider


PHENOMENON_TO_IDEA_PROMPT = """You are a research scientist. You have observed a phenomenon in the literature.
Your job is to generate a research idea that explains and addresses this phenomenon.

Domain: {domain}
Phenomenon: {phenomenon_description}
Evidence: {evidence}
Unexplained by: {unexplained_by}
Potential causes: {potential_causes}

Generate ONE research idea that:
1. Takes this phenomenon as its starting point (not a keyword or topic)
2. Proposes a falsifiable hypothesis about the root cause
3. Proposes a method that addresses the root cause
4. Makes a clear contribution that no prior work makes

The idea must be phenomenon-driven, not method-driven.
BAD: "We propose method X for domain Y" (method-driven)
GOOD: "We observe phenomenon P. We hypothesize cause C. We propose method M to address C." (phenomenon-driven)

Output JSON:
{{
  "title": "concise paper title",
  "hypothesis": "the falsifiable claim (what we claim is true and can be tested)",
  "proposed_method": "what we propose to do (1-2 paragraphs)",
  "expected_contribution": "what this adds that no prior work does",
  "key_experiments": ["experiment 1", "experiment 2", "experiment 3"],
  "potential_venues": ["venue 1", "venue 2"]
}}
"""

EXTENSION_PROMPT = """You are a research scientist extending an existing project.

Existing project:
Domain: {domain}
Current method: {current_method}
Current results: {current_results}
Known limitations: {limitations}

Generate {n} follow-up research directions. Each should:
1. Build on the existing work but make a distinct new contribution
2. Address a specific limitation or open question
3. Be feasible as a standalone paper

For each direction, output:
{{
  "title": "...",
  "phenomenon": "what new phenomenon or gap this addresses",
  "hypothesis": "the falsifiable claim",
  "proposed_method": "what to do",
  "expected_contribution": "what's new",
  "relationship_to_existing": "how it builds on the current work"
}}

Output JSON array of {n} directions.
"""

TRANSFER_TO_IDEA_PROMPT = """You are a research scientist. You have identified a structural analogy
between two domains. Generate a research idea based on this analogy.

Analogy:
Source domain: {source_domain}
Target domain: {target_domain}
Source problem: {source_problem}
Target problem: {target_problem}
Structural similarity: {structural_similarity}
Transfer method: {transfer_method}
Adaptation required: {adaptation_required}

Generate a research idea that:
1. Takes the analogy as its starting point
2. Clearly explains why the transfer is non-trivial (not just applying A to B)
3. Identifies what needs to change for the transfer to work
4. Makes a clear contribution

Output JSON:
{{
  "title": "...",
  "phenomenon": "the problem in the target domain that motivates this",
  "hypothesis": "the falsifiable claim",
  "proposed_method": "what to do (including the adaptation)",
  "expected_contribution": "what's new beyond just applying the source method",
  "key_challenge": "the main technical challenge in the transfer"
}}
"""


class IdeaGenerator:
    def __init__(self, config: LabConfig, llm: LLMProvider, lit: LiteratureProvider):
        self.config = config
        self.llm = llm
        self.lit = lit

    async def from_phenomenon(self, domain: str, phenomenon: Phenomenon) -> Idea | None:
        """Generate an idea from an observed phenomenon."""
        response = await self.llm.complete(
            self.config.architect(),
            [{"role": "user", "content": PHENOMENON_TO_IDEA_PROMPT.format(
                domain=domain,
                phenomenon_description=phenomenon.description,
                evidence=", ".join(phenomenon.evidence[:5]),
                unexplained_by=", ".join(phenomenon.unexplained_by[:3]),
                potential_causes=", ".join(phenomenon.potential_causes[:3]),
            )}],
            temperature=0.6,
            max_tokens=2048,
        )
        data = self._parse_json(response)
        if not data:
            return None

        return Idea(
            id=str(uuid.uuid4())[:8],
            title=data.get("title", "Untitled"),
            domain=domain,
            origin=IdeaOrigin.PHENOMENON,
            phenomenon=phenomenon.description,
            hypothesis=data.get("hypothesis", ""),
            proposed_method=data.get("proposed_method", ""),
            expected_contribution=data.get("expected_contribution", ""),
            metadata={
                "key_experiments": data.get("key_experiments", []),
                "potential_venues": data.get("potential_venues", []),
                "phenomenon_id": phenomenon.id,
            },
        )

    async def from_extension(
        self,
        domain: str,
        current_method: str,
        current_results: str,
        limitations: str,
        n: int = 3,
    ) -> list[Idea]:
        """Generate follow-up ideas from an existing project."""
        response = await self.llm.complete(
            self.config.architect(),
            [{"role": "user", "content": EXTENSION_PROMPT.format(
                domain=domain,
                current_method=current_method,
                current_results=current_results,
                limitations=limitations,
                n=n,
            )}],
            temperature=0.7,
            max_tokens=3000,
        )
        raw_ideas = self._parse_json_array(response)
        ideas = []
        for raw in raw_ideas:
            ideas.append(Idea(
                id=str(uuid.uuid4())[:8],
                title=raw.get("title", "Untitled"),
                domain=domain,
                origin=IdeaOrigin.EXTENSION,
                phenomenon=raw.get("phenomenon", ""),
                hypothesis=raw.get("hypothesis", ""),
                proposed_method=raw.get("proposed_method", ""),
                expected_contribution=raw.get("expected_contribution", ""),
                metadata={"relationship_to_existing": raw.get("relationship_to_existing", "")},
            ))
        return ideas

    async def from_analogy(self, analogy: DomainAnalogy) -> Idea | None:
        """Generate an idea from a cross-domain analogy."""
        response = await self.llm.complete(
            self.config.architect(),
            [{"role": "user", "content": TRANSFER_TO_IDEA_PROMPT.format(
                source_domain=analogy.source_domain,
                target_domain=analogy.target_domain,
                source_problem=analogy.source_problem,
                target_problem=analogy.target_problem,
                structural_similarity=analogy.structural_similarity,
                transfer_method=analogy.transfer_method,
                adaptation_required=analogy.adaptation_required,
            )}],
            temperature=0.6,
            max_tokens=2048,
        )
        data = self._parse_json(response)
        if not data:
            return None

        return Idea(
            id=str(uuid.uuid4())[:8],
            title=data.get("title", "Untitled"),
            domain=analogy.target_domain,
            origin=IdeaOrigin.TRANSFER,
            phenomenon=data.get("phenomenon", analogy.target_problem),
            hypothesis=data.get("hypothesis", ""),
            proposed_method=data.get("proposed_method", ""),
            expected_contribution=data.get("expected_contribution", ""),
            metadata={
                "source_domain": analogy.source_domain,
                "analogy_confidence": analogy.confidence,
                "key_challenge": data.get("key_challenge", ""),
            },
        )

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
