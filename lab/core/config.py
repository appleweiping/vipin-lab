"""Lab configuration — models, thresholds, API keys."""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

# ── Endpoint constants ────────────────────────────────────────────────────────
_KEY_ROTATOR = "http://127.0.0.1:8990/v1"
_KEY_ROTATOR_KEY = "xiangsumao"
_SBBBBB = "http://api.sbbbbbbbbb.xyz/v1"
_SBBBBB_KEY = "REDACTED_SBBBBB_KEY"
_DEEPSEEK = "https://api.deepseek.com/v1"
_DEEPSEEK_KEY = "REDACTED_DEEPSEEK_KEY"


@dataclass
class ModelProfile:
    id: str
    name: str
    role: str
    provider: str = "anthropic"     # anthropic | openai | openrouter | deepseek
    base_url: str = ""              # override endpoint; empty = use provider default
    api_key: str = ""               # override key; empty = use env var
    context_k: int = 200
    cost_per_1m_in: float = 0.0
    cost_per_1m_out: float = 0.0


@dataclass
class LabConfig:
    # ── Model lineup ──────────────────────────────────────────────────────────
    models: list[ModelProfile] = field(default_factory=lambda: [
        ModelProfile(
            id="claude-opus-4-7",
            name="Opus",
            role="architect",
            provider="anthropic",
            base_url=_SBBBBB,
            api_key=_SBBBBB_KEY,
            context_k=1000,
            cost_per_1m_in=15.0,
            cost_per_1m_out=75.0,
        ),
        ModelProfile(
            id="claude-opus-4-7",
            name="Sonnet",
            role="executor",
            provider="anthropic",
            base_url=_SBBBBB,
            api_key=_SBBBBB_KEY,
            context_k=1000,
            cost_per_1m_in=3.0,
            cost_per_1m_out=15.0,
        ),
        ModelProfile(
            id="claude-opus-4-7",
            name="Auditor",
            role="auditor",
            provider="anthropic",
            base_url=_SBBBBB,
            api_key=_SBBBBB_KEY,
            context_k=1000,
            cost_per_1m_in=3.0,
            cost_per_1m_out=15.0,
        ),
        ModelProfile(
            id="deepseek-chat",
            name="DeepSeek",
            role="screener",
            provider="deepseek",
            base_url=_DEEPSEEK,
            api_key=_DEEPSEEK_KEY,
            context_k=64,
            cost_per_1m_in=0.14,
            cost_per_1m_out=0.28,
        ),
    ])

    # ── Quality gates ─────────────────────────────────────────────────────────
    min_novelty_score: float = 6.0
    min_feasibility_score: float = 6.0
    min_experiment_audit_score: float = 6.0
    min_review_score: float = 7.0
    min_baselines: int = 8
    min_seeds_paper: int = 20
    min_seeds_diagnostic: int = 3
    min_citations: int = 30

    # ── Phenomenon detection ──────────────────────────────────────────────────
    phenomenon_severity_threshold: float = 0.5
    max_phenomena_per_session: int = 10

    # ── Analogy engine ────────────────────────────────────────────────────────
    min_analogy_confidence: float = 0.6
    max_analogies_per_idea: int = 5

    # ── Pipeline ──────────────────────────────────────────────────────────────
    max_kill_iterations: int = 3
    max_review_iterations: int = 3
    workspace_root: str = "D:/research/vipin-lab/workspace"

    # ── API keys (env var fallbacks) ──────────────────────────────────────────
    @property
    def anthropic_key(self) -> str:
        return os.environ.get("ANTHROPIC_API_KEY", _KEY_ROTATOR_KEY)

    @property
    def openai_key(self) -> str:
        return os.environ.get("OPENAI_API_KEY", "")

    @property
    def semantic_scholar_key(self) -> str:
        return os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")

    def get_model(self, role: str) -> ModelProfile:
        for m in self.models:
            if m.role == role:
                return m
        return self.models[0]

    def architect(self) -> ModelProfile:
        return self.get_model("architect")

    def executor(self) -> ModelProfile:
        return self.get_model("executor")

    def auditor(self) -> ModelProfile:
        return self.get_model("auditor")

    def screener(self) -> ModelProfile:
        return self.get_model("screener")



@dataclass
class LabConfig:
    # ── Model lineup ──────────────────────────────────────────────────────────
    models: list[ModelProfile] = field(default_factory=lambda: [
        ModelProfile(
            id="claude-opus-4-7",
            name="Opus",
            role="architect",
            provider="anthropic",
            context_k=1000,
            cost_per_1m_in=15.0,
            cost_per_1m_out=75.0,
        ),
        ModelProfile(
            id="claude-opus-4-7",
            name="Sonnet",
            role="executor",
            provider="anthropic",
            context_k=1000,
            cost_per_1m_in=15.0,
            cost_per_1m_out=75.0,
        ),
        ModelProfile(
            id="claude-opus-4-7",
            name="Auditor",
            role="auditor",
            provider="anthropic",
            context_k=1000,
            cost_per_1m_in=15.0,
            cost_per_1m_out=75.0,
        ),
        ModelProfile(
            id="claude-opus-4-7",
            name="Screener",
            role="screener",
            provider="anthropic",
            context_k=1000,
            cost_per_1m_in=15.0,
            cost_per_1m_out=75.0,
        ),
    ])

    # ── Quality gates ─────────────────────────────────────────────────────────
    min_novelty_score: float = 6.0          # idea must score ≥6 to proceed
    min_feasibility_score: float = 6.0
    min_experiment_audit_score: float = 6.0  # all dimensions
    min_review_score: float = 7.0           # auto-review-loop
    min_baselines: int = 8                  # minimum baselines for paper results
    min_seeds_paper: int = 20               # seeds for paper_result label
    min_seeds_diagnostic: int = 3           # seeds for diagnostic label
    min_citations: int = 30                 # minimum citations for top venue

    # ── Phenomenon detection ──────────────────────────────────────────────────
    phenomenon_severity_threshold: float = 0.5   # only track phenomena above this
    max_phenomena_per_session: int = 10

    # ── Analogy engine ────────────────────────────────────────────────────────
    min_analogy_confidence: float = 0.6
    max_analogies_per_idea: int = 5

    # ── Pipeline ──────────────────────────────────────────────────────────────
    max_kill_iterations: int = 3        # max rounds of kill-first before giving up
    max_review_iterations: int = 3      # max auto-review-loop iterations
    workspace_root: str = "D:/research/vipin-lab/workspace"

    # ── API keys ──────────────────────────────────────────────────────────────
    @property
    def anthropic_key(self) -> str:
        return os.environ.get("ANTHROPIC_API_KEY", "")

    @property
    def openai_key(self) -> str:
        return os.environ.get("OPENAI_API_KEY", "")

    @property
    def semantic_scholar_key(self) -> str:
        return os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")

    def get_model(self, role: str) -> ModelProfile:
        for m in self.models:
            if m.role == role:
                return m
        return self.models[0]

    def architect(self) -> ModelProfile:
        return self.get_model("architect")

    def executor(self) -> ModelProfile:
        return self.get_model("executor")

    def auditor(self) -> ModelProfile:
        return self.get_model("auditor")

    def screener(self) -> ModelProfile:
        return self.get_model("screener")
