"""
Vipin Lab Orchestrator.

Runs the full pipeline or individual phases.
Manages workspace, session state, and audit trail.
"""
from __future__ import annotations
import json
import uuid
from datetime import datetime
from pathlib import Path
from ..core.models import (
    Idea, IdeaStatus, IdeaOrigin, LabSession, ExperimentPlan, Paper
)
from ..core.config import LabConfig
from ..providers.llm import LLMProvider
from ..providers.literature import LiteratureProvider
from ..engines.phenomenon import PhenomenonObservatory
from ..engines.analogy import AnalogicalBridge
from ..engines.kill_first import KillFirstEngine
from ..engines.evidence import EvidenceGate
from ..phases.p1_ideation import IdeaGenerator
from ..phases.p2_refine import ResearchRefine
from ..phases.p3_experiment_plan import ExperimentPlanner
from ..phases.p4_bridge import ExperimentBridge
from ..phases.p5_paper_write import PaperWriter
from ..phases.p6_review import AutoReviewLoop
from ..phases.p7_p8_audit import CitationAudit, PaperClaimAudit


class LabOrchestrator:
    def __init__(self, config: LabConfig):
        self.config = config
        self.llm = LLMProvider(config)
        self.lit = LiteratureProvider(config.semantic_scholar_key)

        # Engines
        self.observatory = PhenomenonObservatory(config, self.llm, self.lit)
        self.bridge = AnalogicalBridge(config, self.llm, self.lit)
        self.kill_first = KillFirstEngine(config, self.llm, self.lit)
        self.evidence_gate = EvidenceGate(config, self.llm)

        # Phases
        self.ideator = IdeaGenerator(config, self.llm, self.lit)
        self.refiner = ResearchRefine(config, self.llm, self.lit)
        self.planner = ExperimentPlanner(config, self.llm)
        self.exp_bridge = ExperimentBridge(config, self.llm)
        self.writer = PaperWriter(config, self.llm, self.lit)
        self.reviewer = AutoReviewLoop(config, self.llm)
        self.citation_auditor = CitationAudit(config, self.llm, self.lit)
        self.claim_auditor = PaperClaimAudit(config, self.llm)

    # ── Discovery modes ───────────────────────────────────────────────────────

    async def discover(self, domain: str) -> LabSession:
        """
        Full discovery pipeline:
        1. Scan for phenomena
        2. Generate ideas from top phenomena
        3. Kill-first evaluation
        4. Return ranked surviving ideas
        """
        session = self._new_session("discover", domain, domain)

        # Step 1: Phenomenon scan
        session.log("phenomenon_scan", domain=domain)
        phenomena = await self.observatory.scan(domain)
        session.phenomena = phenomena
        session.log("phenomena_found", count=len(phenomena))

        # Step 2: Generate ideas from top phenomena
        ideas = []
        for phenomenon in phenomena[:3]:  # top 3 phenomena
            idea = await self.ideator.from_phenomenon(domain, phenomenon)
            if idea:
                idea.workspace_dir = str(
                    Path(self.config.workspace_root) / "ideas" / idea.id
                )
                ideas.append(idea)

        session.log("ideas_generated", count=len(ideas))

        # Step 3: Kill-first evaluation (parallel)
        import asyncio
        results = await asyncio.gather(*[self.kill_first.evaluate(idea) for idea in ideas])
        surviving = [(idea, survived) for idea, survived in results if survived]
        session.ideas = [idea for idea, _ in results]
        session.log("kill_first_complete", surviving=len(surviving), killed=len(ideas) - len(surviving))

        # Save session
        self._save_session(session)
        return session

    async def extend(
        self,
        domain: str,
        current_method: str,
        current_results: str,
        limitations: str,
        n: int = 3,
    ) -> LabSession:
        """Generate follow-up ideas from an existing project."""
        session = self._new_session("extend", domain, current_method[:50])

        ideas = await self.ideator.from_extension(
            domain, current_method, current_results, limitations, n
        )
        for idea in ideas:
            idea.workspace_dir = str(
                Path(self.config.workspace_root) / "ideas" / idea.id
            )

        # Kill-first evaluation
        import asyncio
        results = await asyncio.gather(*[self.kill_first.evaluate(idea) for idea in ideas])
        session.ideas = [idea for idea, _ in results]
        session.log("extension_ideas", total=len(ideas),
                    surviving=sum(1 for _, s in results if s))

        self._save_session(session)
        return session

    async def transfer(self, source_domain: str, target_domain: str) -> LabSession:
        """Find cross-domain analogies and generate transfer ideas."""
        session = self._new_session("transfer", target_domain,
                                    f"{source_domain} → {target_domain}")

        # Find analogies
        analogies = await self.bridge.scan_transfers(source_domain, target_domain)
        session.analogies = analogies
        session.log("analogies_found", count=len(analogies))

        # Generate ideas from analogies
        ideas = []
        for analogy in analogies[:3]:
            idea = await self.ideator.from_analogy(analogy)
            if idea:
                idea.workspace_dir = str(
                    Path(self.config.workspace_root) / "ideas" / idea.id
                )
                ideas.append(idea)

        # Kill-first
        import asyncio
        results = await asyncio.gather(*[self.kill_first.evaluate(idea) for idea in ideas])
        session.ideas = [idea for idea, _ in results]
        session.log("transfer_ideas", total=len(ideas),
                    surviving=sum(1 for _, s in results if s))

        self._save_session(session)
        return session

    # ── Full pipeline ─────────────────────────────────────────────────────────

    async def run_pipeline(self, idea: Idea) -> tuple[Idea, Paper | None]:
        """
        Run the full ARIS pipeline on a surviving idea.
        Returns (idea, paper) — paper is None if pipeline fails at any gate.
        """
        # Phase 2: Research refine
        idea, passed = await self.refiner.run(idea)
        if not passed:
            return idea, None

        # Phase 3: Experiment plan
        plan, _ = await self.planner.run(idea)
        if not plan:
            return idea, None

        # Audit the plan (evidence gate)
        scores = await self.evidence_gate.audit_plan(plan)
        if not plan.approved:
            idea.status = IdeaStatus.KILLED
            return idea, None

        idea.status = IdeaStatus.PLANNED

        # Phase 4: Experiment bridge (code skeleton)
        await self.exp_bridge.run(idea, plan)

        # NOTE: Experiments are run by the user (local or server).
        # The pipeline pauses here and resumes after results are available.
        # For now, we continue with placeholder results.
        idea.status = IdeaStatus.RUNNING

        # Phase 5: Paper write
        paper = await self.writer.run(idea, plan)

        # Extract and validate claims
        await self.evidence_gate.extract_claims(paper)

        idea.status = IdeaStatus.WRITING

        # Phase 6: Auto review loop
        paper, review_passed = await self.reviewer.run(idea, paper)
        if not review_passed:
            return idea, paper

        idea.status = IdeaStatus.REVIEWED

        # Phase 7: Citation audit
        citation_passed, citation_issues = await self.citation_auditor.run(idea, paper)

        # Phase 8: Claim audit
        claim_passed, claim_issues = await self.claim_auditor.run(idea, paper)

        if citation_passed and claim_passed:
            idea.status = IdeaStatus.READY

        return idea, paper

    # ── Utilities ─────────────────────────────────────────────────────────────

    def _new_session(self, mode: str, domain: str, seed_input: str) -> LabSession:
        session_id = str(uuid.uuid4())[:8]
        workspace = str(Path(self.config.workspace_root) / session_id)
        Path(workspace).mkdir(parents=True, exist_ok=True)
        return LabSession(
            id=session_id,
            mode=mode,
            domain=domain,
            seed_input=seed_input,
            workspace_dir=workspace,
        )

    def _save_session(self, session: LabSession):
        path = Path(session.workspace_dir) / "session.json"
        data = {
            "id": session.id,
            "mode": session.mode,
            "domain": session.domain,
            "seed_input": session.seed_input,
            "created_at": session.created_at,
            "ideas": [
                {
                    "id": i.id,
                    "title": i.title,
                    "origin": i.origin.value,
                    "status": i.status.value,
                    "novelty_score": i.novelty_score,
                    "feasibility_score": i.feasibility_score,
                    "phenomenon": i.phenomenon[:200],
                    "hypothesis": i.hypothesis[:200],
                    "kill_survived": i.kill_argument.survived if i.kill_argument else None,
                }
                for i in session.ideas
            ],
            "phenomena_count": len(session.phenomena),
            "analogies_count": len(session.analogies),
            "audit_trail": session.audit_trail,
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
