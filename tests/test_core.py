"""Tests for vipin-lab core modules."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import tempfile
import json


# ── Models ────────────────────────────────────────────────────────────────────

def test_idea_is_viable():
    from lab.core.models import Idea, IdeaOrigin
    idea = Idea(
        id="test01",
        title="Test Idea",
        domain="LLM4Rec",
        origin=IdeaOrigin.PHENOMENON,
        phenomenon="test phenomenon",
        hypothesis="test hypothesis",
        proposed_method="test method",
        expected_contribution="test contribution",
        novelty_score=7.0,
        feasibility_score=6.5,
    )
    assert idea.is_viable() is True

    idea.novelty_score = 5.9
    assert idea.is_viable() is False

    idea.novelty_score = 7.0
    idea.feasibility_score = 5.9
    assert idea.is_viable() is False


def test_evidence_label_ordering():
    from lab.core.models import EvidenceLabel
    assert EvidenceLabel.PAPER_RESULT.value == "paper_result"
    assert EvidenceLabel.PILOT.value == "pilot"


# ── Config ────────────────────────────────────────────────────────────────────

def test_lab_config_defaults():
    from lab.core.config import LabConfig
    config = LabConfig()
    assert config.min_novelty_score == 6.0
    assert config.min_baselines == 8
    assert config.min_seeds_paper == 20
    assert len(config.models) == 4


def test_lab_config_model_roles():
    from lab.core.config import LabConfig
    config = LabConfig()
    assert config.architect().role == "architect"
    assert config.executor().role == "executor"
    assert config.auditor().role == "auditor"
    assert config.screener().role == "screener"


# ── Domain Config ─────────────────────────────────────────────────────────────

def test_domain_config_llm4rec():
    from lab.core.domain_config import get_domain_config
    cfg = get_domain_config("LLM4Rec")
    assert cfg is not None
    assert len(cfg.canonical_baselines) >= 8
    assert "HR@10" in cfg.canonical_metrics


def test_domain_config_fuzzy_match():
    from lab.core.domain_config import get_domain_config
    cfg = get_domain_config("recommendation with LLMs")
    # Should match llm4rec or return None — either is acceptable
    # Just verify no crash
    assert cfg is None or cfg.name is not None


def test_domain_config_unknown():
    from lab.core.domain_config import get_domain_config
    cfg = get_domain_config("quantum computing")
    assert cfg is None


# ── Workspace Manager ─────────────────────────────────────────────────────────

def test_workspace_manager_create_and_load():
    from lab.core.config import LabConfig
    from lab.core.models import Idea, IdeaOrigin, IdeaStatus
    from lab.workspace.manager import WorkspaceManager

    with tempfile.TemporaryDirectory() as tmpdir:
        config = LabConfig()
        config.workspace_root = tmpdir
        manager = WorkspaceManager(config)
        manager.setup()

        idea = Idea(
            id="abc12345",
            title="Test Idea",
            domain="LLM4Rec",
            origin=IdeaOrigin.PHENOMENON,
            phenomenon="test",
            hypothesis="test hypothesis",
            proposed_method="test method",
            expected_contribution="test contribution",
        )
        manager.create_idea_workspace(idea)
        manager.save_idea(idea)

        loaded = manager.load_idea("abc12345")
        assert loaded is not None
        assert loaded.title == "Test Idea"
        assert loaded.domain == "LLM4Rec"
        assert loaded.origin == IdeaOrigin.PHENOMENON


def test_workspace_manager_invalid_origin():
    from lab.core.config import LabConfig
    from lab.core.models import Idea, IdeaOrigin
    from lab.workspace.manager import WorkspaceManager

    with tempfile.TemporaryDirectory() as tmpdir:
        config = LabConfig()
        config.workspace_root = tmpdir
        manager = WorkspaceManager(config)
        manager.setup()

        idea = Idea(
            id="xyz99999",
            title="Test",
            domain="test",
            origin=IdeaOrigin.PHENOMENON,
            phenomenon="p",
            hypothesis="h",
            proposed_method="m",
            expected_contribution="c",
        )
        manager.create_idea_workspace(idea)

        # Corrupt the JSON with invalid origin
        idea_file = Path(idea.workspace_dir) / "idea.json"
        data = json.loads(idea_file.read_text())
        data["origin"] = "invalid_origin_value"
        idea_file.write_text(json.dumps(data))

        # Should not crash, should default to PHENOMENON
        loaded = manager.load_idea("xyz99999")
        assert loaded is not None
        assert loaded.origin == IdeaOrigin.PHENOMENON


def test_workspace_stage_detection():
    from lab.core.config import LabConfig
    from lab.core.models import Idea, IdeaOrigin
    from lab.workspace.manager import WorkspaceManager

    with tempfile.TemporaryDirectory() as tmpdir:
        config = LabConfig()
        config.workspace_root = tmpdir
        manager = WorkspaceManager(config)
        manager.setup()

        idea = Idea(
            id="stage01",
            title="Stage Test",
            domain="test",
            origin=IdeaOrigin.PHENOMENON,
            phenomenon="p",
            hypothesis="h",
            proposed_method="m",
            expected_contribution="c",
        )
        manager.create_idea_workspace(idea)
        manager.save_idea(idea)

        stage = manager.get_pipeline_stage(idea)
        assert stage == "kill_tested"


# ── Results Loader ────────────────────────────────────────────────────────────

def test_results_loader_empty_dir():
    from lab.core.models import ExperimentPlan, ExperimentBlock
    from lab.results.loader import ResultLoader

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create empty results dir
        results_dir = Path(tmpdir) / "experiments" / "results"
        results_dir.mkdir(parents=True)

        loader = ResultLoader(tmpdir)
        plan = ExperimentPlan(
            idea_id="test",
            blocks=[],
            compute_estimate_hours=10,
            seed_strategy="",
            fairness_constraints=[],
            milestone_gates=[],
        )
        loaded, warnings = loader.load_into_plan(plan)
        assert loaded is False
        assert any("empty" in w.lower() for w in warnings)


def test_results_loader_missing_dir():
    from lab.core.models import ExperimentPlan
    from lab.results.loader import ResultLoader

    with tempfile.TemporaryDirectory() as tmpdir:
        loader = ResultLoader(tmpdir)
        plan = ExperimentPlan(
            idea_id="test",
            blocks=[],
            compute_estimate_hours=10,
            seed_strategy="",
            fairness_constraints=[],
            milestone_gates=[],
        )
        loaded, warnings = loader.load_into_plan(plan)
        assert loaded is False
        assert len(warnings) > 0


# ── Memory Store ──────────────────────────────────────────────────────────────

def test_memory_store_save_load():
    from lab.memory.store import LabMemory, IdeaRecord

    with tempfile.TemporaryDirectory() as tmpdir:
        memory = LabMemory(tmpdir)
        record = IdeaRecord(
            idea_id="mem01",
            title="Memory Test",
            domain="LLM4Rec",
            origin="phenomenon",
            phenomenon="test phenomenon",
            hypothesis="test hypothesis",
            novelty_score=7.5,
            feasibility_score=6.0,
            final_status="refined",
            killed_at_phase="",
            kill_reason="",
        )
        memory.record_idea(record)

        # Reload from disk
        memory2 = LabMemory(tmpdir)
        prior = memory2.get_prior_ideas("LLM4Rec")
        assert len(prior) == 1
        assert prior[0]["title"] == "Memory Test"


def test_memory_store_domain_lessons():
    from lab.memory.store import LabMemory

    with tempfile.TemporaryDirectory() as tmpdir:
        memory = LabMemory(tmpdir)
        memory.add_lesson("LLM4Rec", "Conformal prediction works well here", "idea01", 0.8)
        memory.add_lesson("NLP", "BERT baselines are essential", "idea02", 0.9)

        lessons = memory.get_domain_lessons("LLM4Rec")
        assert len(lessons) == 1
        assert "Conformal" in lessons[0]


# ── Novelty Checker ───────────────────────────────────────────────────────────

def test_novelty_checker_similarity_bounds():
    from lab.novelty.checker import NoveltyChecker
    from lab.providers.literature import LiteratureProvider, Paper

    checker = NoveltyChecker(LiteratureProvider())

    from lab.core.models import Idea, IdeaOrigin
    idea = Idea(
        id="nov01",
        title="Conformal Prediction for LLM Recommendation",
        domain="LLM4Rec",
        origin=IdeaOrigin.PHENOMENON,
        phenomenon="calibration cliff at rank 5",
        hypothesis="conformal prediction provides coverage guarantees",
        proposed_method="apply conformal prediction to recommendation depth",
        expected_contribution="formal coverage guarantees",
    )
    paper = Paper(
        title="Conformal Prediction for LLM Recommendation",
        abstract="We apply conformal prediction to recommendation depth",
        authors=["Author A"],
        year=2024,
        venue="RecSys",
        paper_id="test123",
    )
    sim = checker._compute_similarity(idea, paper)
    assert 0.0 <= sim <= 1.0


# ── Evidence Gate ─────────────────────────────────────────────────────────────

def test_evidence_gate_empty_response():
    """Evidence gate must not approve plans when LLM returns empty response."""
    from lab.core.config import LabConfig
    from lab.core.models import ExperimentPlan
    from lab.engines.evidence import EvidenceGate
    from lab.providers.llm import LLMProvider

    config = LabConfig()
    llm = MagicMock(spec=LLMProvider)
    llm.complete = AsyncMock(return_value="")  # Empty response

    gate = EvidenceGate(config, llm)
    plan = ExperimentPlan(
        idea_id="test",
        blocks=[],
        compute_estimate_hours=10,
        seed_strategy="",
        fairness_constraints=[],
        milestone_gates=[],
    )

    scores = asyncio.run(gate.audit_plan(plan))
    assert plan.approved is False
    assert all(v == 0.0 for v in scores.values())


# ── Progress Reporter ─────────────────────────────────────────────────────────

def test_progress_reporter_events():
    from lab.core.progress import ProgressReporter, ProgressEvent

    events = []
    reporter = ProgressReporter(verbose=True)
    reporter._callbacks = [lambda e: events.append(e)]  # replace default

    reporter.phase("test_phase", "testing")
    reporter.step("step 1", "detail")
    reporter.done("summary")

    assert len(events) == 3
    assert events[0].phase == "test_phase"
    assert events[1].step == "step 1"
    assert events[2].step.startswith("✓")
