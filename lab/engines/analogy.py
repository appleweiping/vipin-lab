"""
Analogical Bridge Engine.

Cross-domain method transfer via deep structural analogy.

NOT graph traversal. NOT keyword matching.
This engine reasons about WHY a method works in domain A,
then asks whether the same structural problem exists in domain B.

Example:
- Conformal prediction in NLP: provides coverage guarantees on set-valued predictions
- LLM4Rec: models produce ranked lists but confidence is uncalibrated
- Structural analogy: both involve set-valued outputs with coverage requirements
- Transfer: apply conformal prediction to recommendation depth

The engine:
1. Analyzes the source method's structural role (what problem does it solve, why does it work)
2. Searches for the same structural problem in the target domain
3. Identifies what needs to change for the transfer to work
4. Scores analogy confidence
"""
from __future__ import annotations
import json
import re
from ..core.models import DomainAnalogy
from ..core.config import LabConfig
from ..providers.llm import LLMProvider
from ..providers.literature import LiteratureProvider


ANALOGY_ANALYSIS_PROMPT = """You are an expert in cross-domain scientific reasoning.

Source domain: {source_domain}
Source method/concept: {source_method}

Step 1: Analyze the source method structurally.
- What fundamental problem does it solve? (not the surface description, the deep structure)
- What mathematical/conceptual properties make it work?
- What assumptions does it require?
- What would break if those assumptions don't hold?

Step 2: Identify the structural essence.
- Reduce the method to its core structural role in 1-2 sentences
- What class of problems does this structural role apply to?

Output JSON:
{{
  "surface_description": "what the method does on the surface",
  "structural_role": "the deep structural problem it solves",
  "key_properties": ["property 1", "property 2"],
  "required_assumptions": ["assumption 1", "assumption 2"],
  "failure_conditions": ["when it breaks"]
}}
"""

ANALOGY_TRANSFER_PROMPT = """You are reasoning about whether a method from one domain can transfer to another.

Source domain: {source_domain}
Source method structural role: {structural_role}
Source key properties: {key_properties}

Target domain: {target_domain}
Target domain context:
{target_context}

Question: Does the target domain have the same structural problem that the source method solves?

Reason carefully:
1. What is the analogous problem in the target domain?
2. Do the key properties hold in the target domain?
3. What needs to change for the transfer to work?
4. What is the expected benefit if the transfer succeeds?
5. What are the risks / why it might not work?

Rate your confidence in this analogy (0.0-1.0).

Output JSON:
{{
  "target_problem": "the analogous problem in the target domain",
  "structural_similarity": "why the analogy holds",
  "properties_that_hold": ["property 1"],
  "properties_that_dont_hold": ["property 2"],
  "adaptation_required": "what needs to change",
  "expected_benefit": "what we gain if it works",
  "risks": ["risk 1", "risk 2"],
  "confidence": 0.0-1.0,
  "verdict": "strong/moderate/weak/no_analogy"
}}
"""


class AnalogicalBridge:
    def __init__(self, config: LabConfig, llm: LLMProvider, lit: LiteratureProvider):
        self.config = config
        self.llm = llm
        self.lit = lit

    async def find_transfers(
        self,
        source_domain: str,
        source_method: str,
        target_domain: str,
    ) -> list[DomainAnalogy]:
        """Find structural analogies that enable method transfer."""
        import uuid

        # Step 1: Analyze source method structurally
        analysis_response = await self.llm.complete(
            self.config.architect(),
            [{"role": "user", "content": ANALOGY_ANALYSIS_PROMPT.format(
                source_domain=source_domain,
                source_method=source_method,
            )}],
            temperature=0.3,
            max_tokens=2048,
        )
        analysis = self._parse_json(analysis_response)
        if not analysis:
            return []

        # Step 2: Get target domain context
        target_papers = await self.lit.search(
            f"{target_domain} challenges limitations open problems", limit=10
        )
        target_context = self.lit.format_for_prompt(target_papers, max_papers=8)

        # Step 3: Reason about transfer
        transfer_response = await self.llm.complete(
            self.config.architect(),
            [{"role": "user", "content": ANALOGY_TRANSFER_PROMPT.format(
                source_domain=source_domain,
                structural_role=analysis.get("structural_role", ""),
                key_properties=json.dumps(analysis.get("key_properties", [])),
                target_domain=target_domain,
                target_context=target_context,
            )}],
            temperature=0.3,
            max_tokens=2048,
        )
        transfer = self._parse_json(transfer_response)
        if not transfer:
            return []

        confidence = float(transfer.get("confidence", 0))
        verdict = transfer.get("verdict", "no_analogy")

        if verdict == "no_analogy" or confidence < self.config.min_analogy_confidence:
            return []

        analogy = DomainAnalogy(
            source_domain=source_domain,
            target_domain=target_domain,
            source_problem=analysis.get("structural_role", ""),
            target_problem=transfer.get("target_problem", ""),
            structural_similarity=transfer.get("structural_similarity", ""),
            transfer_method=source_method,
            adaptation_required=transfer.get("adaptation_required", ""),
            confidence=confidence,
            supporting_evidence=[p.paper_id for p in target_papers[:3]],
        )
        return [analogy]

    async def scan_transfers(
        self,
        source_domain: str,
        target_domain: str,
        n_methods: int = 5,
    ) -> list[DomainAnalogy]:
        """Find multiple methods from source domain that could transfer to target."""
        # First, identify key methods in source domain
        methods_response = await self.llm.complete(
            self.config.executor(),
            [{"role": "user", "content": f"""List the {n_methods} most structurally interesting methods
in {source_domain} that solve fundamental problems (not just incremental improvements).
For each, give: method name, the fundamental problem it solves.
Output JSON array: [{{"name": "...", "problem": "..."}}]"""}],
            temperature=0.4,
            max_tokens=1024,
        )
        methods = self._parse_json_array(methods_response)
        if not methods:
            return []

        # Run transfers in parallel
        import asyncio
        tasks = [
            self.find_transfers(source_domain, m.get("name", ""), target_domain)
            for m in methods
        ]
        results = await asyncio.gather(*tasks)
        analogies = [a for batch in results for a in batch]

        # Sort by confidence
        analogies.sort(key=lambda x: x.confidence, reverse=True)
        return analogies[:self.config.max_analogies_per_idea]

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
