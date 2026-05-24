"""
Phase 4: Experiment Bridge

Translates the experiment plan into executable code.
Generates:
- Runner architecture (config-driven, seed-controlled)
- Baseline wrappers
- Our method implementation skeleton
- Launch scripts
- M0 sanity check

Does NOT run experiments. That's the user's job (local or server).
Writes everything to workspace/experiments/.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from ..core.models import Idea, ExperimentPlan
from ..core.config import LabConfig
from ..providers.llm import LLMProvider


RUNNER_ARCH_PROMPT = """Design the runner architecture for these experiments.

Idea: {title}
Domain: {domain}
Experiment blocks: {blocks_summary}
Baselines: {baselines}
Datasets: {datasets}

Design a config-driven, seed-controlled experiment runner.
Requirements:
1. All hyperparameters in YAML configs (not hardcoded)
2. Seed control: set all random seeds (numpy, torch, random, cuda)
3. Results go to results/ directory (gitignored)
4. Checkpoint strategy for crash recovery
5. Launcher script that runs all blocks
6. Result aggregation script

Output the architecture as a file tree with brief descriptions:
experiments/
  configs/
    base.yaml          — shared config
    block_1.yaml       — block-specific overrides
    ...
  src/
    run.py             — main runner
    baselines/
      baseline_1.py    — baseline wrapper
      ...
    method/
      model.py         — our method
    utils/
      seeds.py         — seed control
      metrics.py       — metric computation
      aggregator.py    — result aggregation
  scripts/
    launch_all.sh      — launch all blocks
    m0_sanity.sh       — M0 sanity check (block 1, 3 seeds)
  results/             — gitignored

Then write the content of:
1. configs/base.yaml
2. src/utils/seeds.py
3. scripts/m0_sanity.sh

Output JSON:
{{
  "file_tree": "...",
  "base_yaml": "...",
  "seeds_py": "...",
  "m0_sanity_sh": "..."
}}
"""

METHOD_SKELETON_PROMPT = """Write a Python skeleton for this research method.

Method: {proposed_method}
Domain: {domain}
Key components: {key_components}

Write a clean, well-structured skeleton with:
1. Class definition with __init__ and forward/predict methods
2. Type hints
3. Docstrings explaining what each method does
4. TODO comments where the actual implementation goes
5. Integration with the runner (how it's called from run.py)

This is a skeleton — mark implementation points with TODO.
Output the Python code directly (no JSON wrapper).
"""


class ExperimentBridge:
    def __init__(self, config: LabConfig, llm: LLMProvider):
        self.config = config
        self.llm = llm

    async def run(self, idea: Idea, plan: ExperimentPlan) -> bool:
        """Generate experiment code skeleton. Returns True if successful."""
        workspace = Path(idea.workspace_dir) if idea.workspace_dir else None
        if not workspace:
            return False

        exp_dir = workspace / "experiments"
        exp_dir.mkdir(parents=True, exist_ok=True)

        # Generate runner architecture
        blocks_summary = "\n".join(
            f"Block {b.id}: {b.name} — {b.hypothesis[:80]}"
            for b in plan.blocks
        )
        baselines = list({b for block in plan.blocks for b in block.baselines})[:10]
        datasets = idea.metadata.get("data_sources", ["standard benchmarks"])

        arch_response = await self.llm.complete(
            self.config.executor(),
            [{"role": "user", "content": RUNNER_ARCH_PROMPT.format(
                title=idea.title,
                domain=idea.domain,
                blocks_summary=blocks_summary,
                baselines=", ".join(baselines),
                datasets=", ".join(datasets),
            )}],
            temperature=0.3,
            max_tokens=4096,
        )
        arch = self._parse_json(arch_response)

        # Write architecture files
        if arch.get("base_yaml"):
            configs_dir = exp_dir / "configs"
            configs_dir.mkdir(exist_ok=True)
            (configs_dir / "base.yaml").write_text(arch["base_yaml"], encoding="utf-8")

        if arch.get("seeds_py"):
            utils_dir = exp_dir / "src" / "utils"
            utils_dir.mkdir(parents=True, exist_ok=True)
            (utils_dir / "seeds.py").write_text(arch["seeds_py"], encoding="utf-8")

        if arch.get("m0_sanity_sh"):
            scripts_dir = exp_dir / "scripts"
            scripts_dir.mkdir(exist_ok=True)
            (scripts_dir / "m0_sanity.sh").write_text(arch["m0_sanity_sh"], encoding="utf-8")

        # Write file tree documentation
        if arch.get("file_tree"):
            (exp_dir / "ARCHITECTURE.md").write_text(
                f"# Experiment Architecture\n\n```\n{arch['file_tree']}\n```\n",
                encoding="utf-8",
            )

        # Generate method skeleton
        method_response = await self.llm.complete(
            self.config.executor(),
            [{"role": "user", "content": METHOD_SKELETON_PROMPT.format(
                proposed_method=idea.proposed_method,
                domain=idea.domain,
                key_components=idea.metadata.get("key_experiments", []),
            )}],
            temperature=0.3,
            max_tokens=3000,
        )
        method_dir = exp_dir / "src" / "method"
        method_dir.mkdir(parents=True, exist_ok=True)
        (method_dir / "model.py").write_text(method_response, encoding="utf-8")

        # Write gitignore for results
        (exp_dir / ".gitignore").write_text("results/\n*.log\n__pycache__/\n*.pyc\n", encoding="utf-8")

        # Write README for experiments
        (exp_dir / "README.md").write_text(
            f"# Experiments: {idea.title}\n\n"
            f"## Quick Start\n\n"
            f"```bash\n"
            f"# M0 sanity check (run first, must pass before scaling)\n"
            f"bash scripts/m0_sanity.sh\n\n"
            f"# Full experiment run\n"
            f"bash scripts/launch_all.sh\n"
            f"```\n\n"
            f"## Blocks\n\n"
            + "\n".join(f"- **Block {b.id}**: {b.name}" for b in plan.blocks)
            + "\n\n"
            f"## M0 Gate\n\n"
            f"Block 1 with 3 seeds must pass before scaling to full experiments.\n"
            f"Kill condition: {plan.blocks[0].kill_condition if plan.blocks else 'TBD'}\n",
            encoding="utf-8",
        )

        return True

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
