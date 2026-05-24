"""
Result Loader — reads experiment outputs back into the pipeline.

After the user runs experiments (locally or on server), this module:
1. Scans workspace/experiments/results/ for output files
2. Validates result format and completeness
3. Merges results back into ExperimentPlan.blocks[].results
4. Assigns evidence labels based on actual seeds/stats found
5. Enables pipeline resumption from Phase 5 onward
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from ..core.models import ExperimentPlan, ExperimentBlock, EvidenceLabel


# Expected result file patterns
RESULT_PATTERNS = [
    "results.json", "metrics.json", "report.json",
    "block_*.json", "results_block*.json",
]


class ResultLoader:
    def __init__(self, workspace_dir: str):
        self.workspace = Path(workspace_dir)
        self.results_dir = self.workspace / "experiments" / "results"

    def load_into_plan(self, plan: ExperimentPlan) -> tuple[bool, list[str]]:
        """
        Load experiment results from disk into plan.blocks[].results.
        Returns (any_loaded, warnings).
        """
        if not self.results_dir.exists():
            return False, [f"Results directory not found: {self.results_dir}"]

        # Check if directory is empty
        result_files = list(self.results_dir.glob("*.json"))
        if not result_files:
            return False, [
                f"Results directory exists but is empty: {self.results_dir}",
                "Run experiments first, then place results/*.json files here.",
            ]

        warnings = []
        any_loaded = False

        for block in plan.blocks:
            loaded, block_warnings = self._load_block(block)
            warnings.extend(block_warnings)
            if loaded:
                any_loaded = True

        return any_loaded, warnings

    def _load_block(self, block: ExperimentBlock) -> tuple[bool, list[str]]:
        """Load results for a single block."""
        warnings = []

        # Try multiple file naming conventions
        candidates = [
            self.results_dir / f"block_{block.id}.json",
            self.results_dir / f"block_{block.id}_results.json",
            self.results_dir / f"results_block{block.id}.json",
            self.results_dir / f"{block.id}.json",
            self.results_dir / "results.json",  # single-file format
        ]

        for path in candidates:
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    # If single-file format, extract this block's results
                    if "blocks" in data:
                        block_data = next(
                            (b for b in data["blocks"] if b.get("id") == block.id), None
                        )
                        if block_data:
                            block.results = block_data.get("results", {})
                    else:
                        block.results = data

                    # Assign evidence label based on actual results
                    block.evidence_label = self._classify_evidence(block)
                    return True, warnings
                except (json.JSONDecodeError, KeyError) as e:
                    warnings.append(f"Block {block.id}: failed to parse {path.name}: {e}")

        warnings.append(f"Block {block.id} ({block.name}): no results file found")
        return False, warnings

    def _classify_evidence(self, block: ExperimentBlock) -> EvidenceLabel:
        """Classify evidence label based on actual results metadata."""
        results = block.results
        if not results:
            return EvidenceLabel.PILOT

        # Check for explicit evidence label in results
        if "_evidence_label" in results:
            try:
                return EvidenceLabel(results["_evidence_label"])
            except ValueError:
                pass

        # Infer from metadata
        seeds = results.get("seeds_used", results.get("n_seeds", 0))
        has_stats = "p_value" in results or "t_statistic" in results
        n_baselines = len(results.get("baselines", {}))
        fair = results.get("fair_comparison", False)

        if seeds >= 20 and has_stats and n_baselines >= 8 and fair:
            return EvidenceLabel.PAPER_RESULT
        elif seeds >= 20 and has_stats:
            return EvidenceLabel.OFFICIAL
        elif seeds >= 3:
            return EvidenceLabel.DIAGNOSTIC
        else:
            return EvidenceLabel.PILOT

    def get_summary(self, plan: ExperimentPlan) -> dict:
        """Get a summary of loaded results."""
        summary = {
            "total_blocks": len(plan.blocks),
            "blocks_with_results": sum(1 for b in plan.blocks if b.results),
            "paper_result_blocks": sum(
                1 for b in plan.blocks if b.evidence_label == EvidenceLabel.PAPER_RESULT
            ),
            "by_label": {},
        }
        for label in EvidenceLabel:
            count = sum(1 for b in plan.blocks if b.evidence_label == label)
            if count:
                summary["by_label"][label.value] = count
        return summary
