"""
Vipin Lab — core data models.

Every research artifact in the lab is typed. No dicts passed around.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


# ── Evidence quality labels (from ARIS) ──────────────────────────────────────

class EvidenceLabel(str, Enum):
    PAPER_RESULT = "paper_result"   # 20+ seeds, statistically valid, fair → main paper
    OFFICIAL     = "official"       # full seeds, needs one more check → almost
    DIAGNOSTIC   = "diagnostic"     # partial seeds / preliminary → supplementary only
    PILOT        = "pilot"          # quick test → never in paper


# ── Idea lifecycle ────────────────────────────────────────────────────────────

class IdeaStatus(str, Enum):
    GENERATED    = "generated"
    KILL_TESTED  = "kill_tested"    # survived kill-first adversarial review
    REFINED      = "refined"        # research-refine passed
    PLANNED      = "planned"        # experiment plan approved
    RUNNING      = "running"        # experiments in progress
    AUDITED      = "audited"        # experiment-audit passed
    WRITING      = "writing"        # paper being written
    REVIEWED     = "reviewed"       # auto-review-loop passed
    READY        = "ready"          # paper-claim-audit passed, ready to submit
    KILLED       = "killed"         # failed a gate, archived


class IdeaOrigin(str, Enum):
    PHENOMENON   = "phenomenon"     # started from observed anomaly
    EXTENSION    = "extension"      # extension of existing project
    TRANSFER     = "transfer"       # cross-domain method transfer
    LITERATURE   = "literature"     # gap found in literature survey
    SERENDIPITY  = "serendipity"    # unexpected connection


@dataclass
class KillArgument:
    """The strongest possible objection to an idea. Must be written before proceeding."""
    argument: str
    closest_prior_work: list[str]   # papers that come closest to killing the idea
    rebuttal: str                   # why the idea survives despite the kill argument
    survived: bool = False
    reviewer_model: str = ""


@dataclass
class Idea:
    id: str
    title: str
    domain: str
    origin: IdeaOrigin
    phenomenon: str                 # the observed anomaly / unexplained result that motivates this
    hypothesis: str                 # the falsifiable claim
    proposed_method: str
    expected_contribution: str      # what this adds that no prior work does
    kill_argument: KillArgument | None = None
    novelty_score: float = 0.0      # 0-10, scored by cross-model review
    feasibility_score: float = 0.0  # 0-10
    status: IdeaStatus = IdeaStatus.GENERATED
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    workspace_dir: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_viable(self) -> bool:
        return self.novelty_score >= 6.0 and self.feasibility_score >= 6.0


# ── Phenomenon ────────────────────────────────────────────────────────────────

@dataclass
class Phenomenon:
    """An observed anomaly, contradiction, or unexplained result in the literature."""
    id: str
    domain: str
    description: str                # what was observed
    evidence: list[str]             # papers / experiments that show this
    unexplained_by: list[str]       # existing methods that fail to explain it
    potential_causes: list[str]     # hypothesized explanations
    severity: float                 # 0-1, how important is this to the field
    discovered_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    source_papers: list[str] = field(default_factory=list)


# ── Cross-domain transfer ─────────────────────────────────────────────────────

@dataclass
class DomainAnalogy:
    """A structural analogy between two domains that enables method transfer."""
    source_domain: str
    target_domain: str
    source_problem: str             # what problem the method solves in source domain
    target_problem: str             # the analogous problem in target domain
    structural_similarity: str      # why the analogy holds (mathematical / conceptual)
    transfer_method: str            # what specifically to transfer
    adaptation_required: str        # what needs to change for the transfer to work
    confidence: float               # 0-1, how strong is the analogy
    supporting_evidence: list[str]  # papers that support the analogy


# ── Experiment ────────────────────────────────────────────────────────────────

class ExperimentStatus(str, Enum):
    PLANNED  = "planned"
    RUNNING  = "running"
    DONE     = "done"
    FAILED   = "failed"


@dataclass
class ExperimentBlock:
    """One block in the experiment plan. Each block answers one sub-question."""
    id: int
    name: str
    hypothesis: str                 # falsifiable claim this block tests
    primary_metrics: list[str]
    secondary_metrics: list[str]
    baselines: list[str]            # minimum 8 for paper results
    seeds: int                      # 20+ for paper_result, 3-5 for diagnostic
    expected_outcome: str
    failure_mode: str               # what would disprove the hypothesis
    kill_condition: str             # concrete threshold: "if effect < X → STOP"
    status: ExperimentStatus = ExperimentStatus.PLANNED
    results: dict[str, Any] = field(default_factory=dict)
    evidence_label: EvidenceLabel = EvidenceLabel.PILOT


@dataclass
class ExperimentPlan:
    idea_id: str
    blocks: list[ExperimentBlock]
    compute_estimate_hours: float
    seed_strategy: str
    fairness_constraints: list[str]  # same data splits, same preprocessing, etc.
    milestone_gates: list[str]       # M0, M1, M2 with concrete pass/fail criteria
    approved: bool = False
    audit_scores: dict[str, float] = field(default_factory=dict)  # Evidence, Rigor, Gates, Feasibility, Paper-potential


# ── Paper ─────────────────────────────────────────────────────────────────────

@dataclass
class Claim:
    text: str
    claim_type: str                 # empirical / novelty / theoretical
    evidence_ids: list[str]         # which experiment blocks support this
    evidence_label: EvidenceLabel
    verified: bool = False


@dataclass
class Paper:
    idea_id: str
    title: str
    abstract: str = ""
    sections: dict[str, str] = field(default_factory=dict)
    claims: list[Claim] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    figures: list[str] = field(default_factory=list)
    latex_path: str = ""
    review_scores: dict[str, float] = field(default_factory=dict)
    claim_audit_passed: bool = False
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


# ── Session ───────────────────────────────────────────────────────────────────

@dataclass
class LabSession:
    id: str
    mode: str                       # discover / extend / transfer / full_pipeline
    domain: str
    seed_input: str                 # the starting point (domain, paper, phenomenon, project)
    ideas: list[Idea] = field(default_factory=list)
    phenomena: list[Phenomenon] = field(default_factory=list)
    analogies: list[DomainAnalogy] = field(default_factory=list)
    active_idea_id: str | None = None
    audit_trail: list[dict] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    workspace_dir: str = ""

    def log(self, step: str, **kwargs):
        self.audit_trail.append({"step": step, "ts": datetime.utcnow().isoformat(), **kwargs})
