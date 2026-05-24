"""
vlab — Vipin Lab CLI

Usage:
  vlab discover "LLM4Rec"                    # scan domain for phenomena → ideas
  vlab extend "LLM4Rec" --method "..." --results "..." --limits "..."
  vlab transfer "conformal prediction" "LLM4Rec"
  vlab pipeline <idea_id>                    # run full pipeline on an idea
  vlab sessions                              # list recent sessions
  vlab show <session_id>                     # show session details
  vlab status                                # check config and API keys
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
import shutil
import textwrap
import time
import threading
import itertools
from pathlib import Path
from typing import Optional
import typer

# Lazy import of IdeaStatus for pipeline command
def _get_idea_status():
    from lab.core.models import IdeaStatus
    return IdeaStatus

# Ensure project root on path
_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

app = typer.Typer(
    name="vlab",
    help="Vipin Lab — Autonomous Research System",
    add_completion=False,
)

# ── ANSI ──────────────────────────────────────────────────────────────────────
R = "\033[0m"; BOLD = "\033[1m"; DIM = "\033[2m"
RED = "\033[31m"; GREEN = "\033[32m"; YELLOW = "\033[33m"
BLUE = "\033[34m"; MAGENTA = "\033[35m"; CYAN = "\033[36m"
BGREEN = "\033[92m"; BYELLOW = "\033[93m"; BCYAN = "\033[96m"; BMAGENTA = "\033[95m"

def c(*args):
    codes = [a for a in args if isinstance(a, str) and a.startswith("\033")]
    texts = [a for a in args if not (isinstance(a, str) and a.startswith("\033"))]
    return "".join(codes) + str(texts[0] if texts else "") + R

def hr(char="─", width=None):
    w = width or min(shutil.get_terminal_size().columns, 88)
    return c(char * w, DIM)

def wrap(text: str, indent: str = "  ") -> str:
    w = min(shutil.get_terminal_size().columns - 4, 84)
    lines = []
    for para in str(text).split("\n"):
        if not para.strip():
            lines.append("")
        else:
            lines.extend(textwrap.wrap(para, w, initial_indent=indent, subsequent_indent=indent))
    return "\n".join(lines)


class Spinner:
    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    def __init__(self, msg: str, color: str = CYAN):
        self.msg = msg; self.color = color
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t0 = 0.0
    def _run(self):
        for f in itertools.cycle(self.FRAMES):
            if self._stop.is_set(): break
            elapsed = time.time() - self._t0
            sys.stdout.write(f"\r  {c(f, self.color)} {self.msg}  {c(f'{elapsed:.0f}s', DIM)}  ")
            sys.stdout.flush()
            time.sleep(0.08)
        sys.stdout.write("\r" + " " * 60 + "\r"); sys.stdout.flush()
    def __enter__(self): self._t0 = time.time(); self._t.start(); return self
    def __exit__(self, *_): self._stop.set(); self._t.join()


def print_header():
    print(f"\n  {c('⚗ Vipin Lab', BOLD, BMAGENTA)}  {c('v1.0', DIM)}")
    print(c("  Autonomous Research System — Phenomenon-Driven Discovery", DIM))
    print(hr())


def print_idea(idea, index: int = 0):
    status_colors = {
        "generated": DIM, "kill_tested": BYELLOW, "refined": BGREEN,
        "planned": BCYAN, "running": BCYAN, "ready": BGREEN, "killed": RED,
    }
    sc = status_colors.get(idea.get("status", ""), DIM)
    origin_icons = {
        "phenomenon": "🔬", "extension": "🔗", "transfer": "⚡", "literature": "📚"
    }
    icon = origin_icons.get(idea.get("origin", ""), "💡")

    print(f"\n  {c(f'#{index+1}', BOLD, DIM)} {icon} {c(idea.get('title', 'Untitled'), BOLD)}")
    print(f"     {c('Status:', DIM)} {c(idea.get('status', '?'), sc)}  "
          f"{c('Novelty:', DIM)} {c(f\"{idea.get('novelty_score', 0):.1f}/10\", BYELLOW)}  "
          f"{c('Feasibility:', DIM)} {c(f\"{idea.get('feasibility_score', 0):.1f}/10\", BGREEN)}")
    if idea.get("phenomenon"):
        print(f"     {c('Phenomenon:', DIM)} {wrap(idea['phenomenon'][:120], indent='').strip()}")
    if idea.get("hypothesis"):
        print(f"     {c('Hypothesis:', DIM)} {wrap(idea['hypothesis'][:120], indent='').strip()}")
    kill = idea.get("kill_survived")
    if kill is not None:
        print(f"     {c('Kill test:', DIM)} {c('survived ✓', BGREEN) if kill else c('killed ✗', RED)}")


def get_orchestrator():
    try:
        from lab.core.config import LabConfig
        from lab.core.orchestrator import LabOrchestrator
        config = LabConfig()
        if not config.anthropic_key:
            typer.echo(c("\n  ✗ ANTHROPIC_API_KEY not set. Add it to .env\n", RED))
            raise typer.Exit(1)
        return LabOrchestrator(config)
    except ImportError as e:
        typer.echo(c(f"\n  ✗ Import error: {e}\n  Run: pip install -e .\n", RED))
        raise typer.Exit(1)


# ── Commands ──────────────────────────────────────────────────────────────────

@app.command()
def discover(
    domain: str = typer.Argument(..., help="Research domain to scan (e.g. 'LLM4Rec')"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full details"),
):
    """Scan a domain for phenomena and generate research ideas."""
    print_header()
    print(f"  {c('Mode:', DIM)} {c('🔬 Phenomenon Discovery', BMAGENTA)}")
    print(f"  {c('Domain:', DIM)} {c(domain, BOLD)}")
    print(hr())

    orchestrator = get_orchestrator()

    with Spinner(f"Scanning {domain} for phenomena and generating ideas", BMAGENTA):
        session = asyncio.run(orchestrator.discover(domain))

    print(f"\n  {c('Session:', DIM)} {c(session.id, DIM)}")
    print(f"  {c('Phenomena found:', DIM)} {c(str(len(session.phenomena)), BYELLOW)}")
    print(f"  {c('Ideas generated:', DIM)} {c(str(len(session.ideas)), BCYAN)}")

    surviving = [i for i in session.ideas if i.kill_argument and i.kill_argument.survived]
    killed = [i for i in session.ideas if i.status.value == "killed"]
    print(f"  {c('Survived kill-first:', DIM)} {c(str(len(surviving)), BGREEN)}")
    print(f"  {c('Killed:', DIM)} {c(str(killed.__len__()), RED)}")
    print(hr())

    if session.phenomena:
        print(f"\n  {c('Top Phenomena', BOLD, BYELLOW)}")
        for i, p in enumerate(session.phenomena[:3]):
            print(f"\n  {c(f'P{i+1}', BOLD, BYELLOW)} {p.description[:100]}")
            if verbose:
                print(f"     Severity: {p.severity:.2f}")
                print(f"     Evidence: {', '.join(p.evidence[:2])}")

    if session.ideas:
        print(f"\n  {c('Ideas', BOLD, BCYAN)}")
        for i, idea in enumerate(session.ideas):
            idea_dict = {
                "title": idea.title, "status": idea.status.value,
                "origin": idea.origin.value, "novelty_score": idea.novelty_score,
                "feasibility_score": idea.feasibility_score,
                "phenomenon": idea.phenomenon, "hypothesis": idea.hypothesis,
                "kill_survived": idea.kill_argument.survived if idea.kill_argument else None,
            }
            print_idea(idea_dict, i)

    print(f"\n  {c('Workspace:', DIM)} {c(session.workspace_dir, DIM)}")
    print(f"  {c('Next step:', DIM)} {c('vlab pipeline <idea_id>', BCYAN)} to run full pipeline\n")


@app.command()
def extend(
    domain: str = typer.Argument(..., help="Research domain"),
    method: str = typer.Option(..., "--method", "-m", help="Current method description"),
    results: str = typer.Option("", "--results", "-r", help="Current results summary"),
    limits: str = typer.Option("", "--limits", "-l", help="Known limitations"),
    n: int = typer.Option(3, "--n", help="Number of ideas to generate"),
):
    """Generate follow-up ideas from an existing project."""
    print_header()
    print(f"  {c('Mode:', DIM)} {c('🔗 Project Extension', BMAGENTA)}")
    print(f"  {c('Domain:', DIM)} {c(domain, BOLD)}")
    print(hr())

    orchestrator = get_orchestrator()

    with Spinner(f"Generating {n} extension ideas", BMAGENTA):
        session = asyncio.run(orchestrator.extend(domain, method, results, limits, n))

    print(f"\n  {c('Ideas generated:', DIM)} {c(str(len(session.ideas)), BCYAN)}")
    surviving = sum(1 for i in session.ideas if i.kill_argument and i.kill_argument.survived)
    print(f"  {c('Survived kill-first:', DIM)} {c(str(surviving), BGREEN)}")
    print(hr())

    for i, idea in enumerate(session.ideas):
        idea_dict = {
            "title": idea.title, "status": idea.status.value,
            "origin": idea.origin.value, "novelty_score": idea.novelty_score,
            "feasibility_score": idea.feasibility_score,
            "phenomenon": idea.phenomenon, "hypothesis": idea.hypothesis,
            "kill_survived": idea.kill_argument.survived if idea.kill_argument else None,
        }
        print_idea(idea_dict, i)

    print(f"\n  {c('Workspace:', DIM)} {c(session.workspace_dir, DIM)}\n")


@app.command()
def transfer(
    source: str = typer.Argument(..., help="Source domain (e.g. 'conformal prediction')"),
    target: str = typer.Argument(..., help="Target domain (e.g. 'LLM4Rec')"),
):
    """Find cross-domain analogies and generate transfer ideas."""
    print_header()
    print(f"  {c('Mode:', DIM)} {c('⚡ Cross-Domain Transfer', BMAGENTA)}")
    print(f"  {c('Source:', DIM)} {c(source, BOLD)}  {c('→', DIM)}  {c('Target:', DIM)} {c(target, BOLD)}")
    print(hr())

    orchestrator = get_orchestrator()

    with Spinner(f"Finding analogies: {source} → {target}", BMAGENTA):
        session = asyncio.run(orchestrator.transfer(source, target))

    print(f"\n  {c('Analogies found:', DIM)} {c(str(len(session.analogies)), BYELLOW)}")
    print(f"  {c('Ideas generated:', DIM)} {c(str(len(session.ideas)), BCYAN)}")
    print(hr())

    if session.analogies:
        print(f"\n  {c('Analogies', BOLD, BYELLOW)}")
        for a in session.analogies[:3]:
            print(f"\n  {c('⚡', BYELLOW)} {c(f'{a.confidence:.0%} confidence', BYELLOW)}")
            print(f"     {c('Source problem:', DIM)} {a.source_problem[:80]}")
            print(f"     {c('Target problem:', DIM)} {a.target_problem[:80]}")
            print(f"     {c('Adaptation:', DIM)} {a.adaptation_required[:80]}")

    for i, idea in enumerate(session.ideas):
        idea_dict = {
            "title": idea.title, "status": idea.status.value,
            "origin": idea.origin.value, "novelty_score": idea.novelty_score,
            "feasibility_score": idea.feasibility_score,
            "phenomenon": idea.phenomenon, "hypothesis": idea.hypothesis,
            "kill_survived": idea.kill_argument.survived if idea.kill_argument else None,
        }
        print_idea(idea_dict, i)

    print(f"\n  {c('Workspace:', DIM)} {c(session.workspace_dir, DIM)}\n")


@app.command()
def pipeline(
    idea_id: str = typer.Argument(..., help="Idea ID from a previous session"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Run the full research pipeline on a surviving idea."""
    print_header()
    print(f"  {c('Mode:', DIM)} {c('🔬 Full Pipeline', BMAGENTA)}")
    print(f"  {c('Idea:', DIM)} {c(idea_id, BOLD)}")
    print(hr())

    orchestrator = get_orchestrator()

    # Load idea from workspace
    idea = orchestrator.workspace.load_idea(idea_id)
    if not idea:
        typer.echo(c(f"\n  ✗ Idea not found: {idea_id}\n  Run 'vlab sessions' to list ideas.\n", RED))
        raise typer.Exit(1)

    stage = orchestrator.workspace.get_pipeline_stage(idea)
    typer.echo(f"  {c('Current stage:', DIM)} {c(stage, BYELLOW)}")
    typer.echo(f"  {c('Status:', DIM)} {c(idea.status.value, BCYAN)}")

    if stage == "experiments_done":
        typer.echo(f"\n  {c('Results detected.', BGREEN)} Resuming from paper-write phase.")
    elif stage == "bridge_done":
        typer.echo(f"\n  {c('⚠ Waiting for experiments.', BYELLOW)}")
        typer.echo(f"  Run experiments in: {idea.workspace_dir}/experiments/")
        typer.echo(f"  Then run: {c('vlab pipeline ' + idea_id, BCYAN)} again to resume.\n")
        raise typer.Exit(0)

    with Spinner(f"Running pipeline from stage: {stage}", BMAGENTA):
        result_idea, paper = asyncio.run(orchestrator.run_pipeline(idea))

    if paper is None:
        IdeaStatus = _get_idea_status()
        if result_idea.status == IdeaStatus.RUNNING:
            typer.echo(f"\n  {c('Pipeline paused.', BYELLOW)} Run experiments then resume.")
            typer.echo(f"  Experiments dir: {result_idea.workspace_dir}/experiments/")
        else:
            typer.echo(c(f"\n  ✗ Pipeline failed at stage: {result_idea.status.value}\n", RED))
        raise typer.Exit(0)

    status_color = BGREEN if result_idea.status == IdeaStatus.READY else BYELLOW
    typer.echo(f"\n  {c('Status:', DIM)} {c(result_idea.status.value, status_color)}")
    if paper:
        typer.echo(f"  {c('Paper:', DIM)} {c(paper.title, BOLD)}")
        typer.echo(f"  {c('Review scores:', DIM)} " +
                   ", ".join(f"{k}: {v:.0f}" for k, v in paper.review_scores.items()))
    typer.echo(f"  {c('Workspace:', DIM)} {c(result_idea.workspace_dir, DIM)}\n")


@app.command()
def resume(
    idea_id: str = typer.Argument(..., help="Idea ID to resume"),
):
    """Resume pipeline for an idea (e.g. after running experiments)."""
    print_header()
    print(f"  {c('Resuming pipeline for:', DIM)} {c(idea_id, BOLD)}")
    print(hr())

    orchestrator = get_orchestrator()

    with Spinner(f"Resuming pipeline: {idea_id}", BMAGENTA):
        idea, paper = asyncio.run(orchestrator.resume_pipeline(idea_id))

    if idea is None:
        typer.echo(c(f"\n  ✗ Idea not found: {idea_id}\n", RED))
        raise typer.Exit(1)

    typer.echo(f"\n  {c('Status:', DIM)} {c(idea.status.value, BGREEN)}")
    if paper:
        typer.echo(f"  {c('Paper:', DIM)} {c(paper.title, BOLD)}")
    typer.echo(f"  {c('Workspace:', DIM)} {c(idea.workspace_dir, DIM)}\n")


@app.command()
def ideas(
    domain: str = typer.Option("", "--domain", "-d", help="Filter by domain"),
    status: str = typer.Option("", "--status", "-s", help="Filter by status"),
):
    """List all ideas across all sessions."""
    orchestrator = get_orchestrator()
    all_ideas = orchestrator.workspace.list_ideas(status_filter=status or None)

    if domain:
        all_ideas = [i for i in all_ideas if domain.lower() in i.get("domain", "").lower()]

    if not all_ideas:
        typer.echo(c("\n  No ideas found.\n", DIM))
        return

    print_header()
    print(f"  {c('All Ideas', BOLD)}  {c(f'({len(all_ideas)} total)', DIM)}")
    print(hr())

    for idea in all_ideas:
        print_idea(idea, 0)
        typer.echo(f"     {c('Stage:', DIM)} {c(idea.get('stage', '?'), BCYAN)}  "
                   f"{c('ID:', DIM)} {c(idea.get('id', '?'), DIM)}")

    print(hr())
    print()


@app.command()
def sessions():
    """List recent lab sessions."""
    workspace_root = Path("workspace")
    if not workspace_root.exists():
        typer.echo(c("\n  No sessions yet.\n", DIM))
        return

    print_header()
    print(f"  {c('Recent Sessions', BOLD)}")
    print(hr())

    session_files = sorted(workspace_root.glob("*/session.json"), reverse=True)[:20]
    if not session_files:
        typer.echo(c("  No sessions found.\n", DIM))
        return

    for f in session_files:
        try:
            data = json.loads(f.read_text())
            mode_icons = {"discover": "🔬", "extend": "🔗", "transfer": "⚡"}
            icon = mode_icons.get(data.get("mode", ""), "💡")
            ts = data.get("created_at", "")[:16].replace("T", " ")
            n_ideas = len(data.get("ideas", []))
            surviving = sum(1 for i in data.get("ideas", []) if i.get("kill_survived"))
            typer.echo(
                f"  {c(data['id'], DIM)}  {c(ts, DIM)}  "
                f"{icon} {c(data.get('mode', '?'), BCYAN):<12}  "
                f"{c(data.get('domain', '?')[:30], BOLD)}  "
                f"{c(f'{surviving}/{n_ideas} ideas', BGREEN)}"
            )
        except Exception:
            pass
    print(hr())


@app.command()
def show(session_id: str = typer.Argument(..., help="Session ID")):
    """Show details of a session."""
    matches = list(Path("workspace").glob(f"{session_id}*/session.json"))
    if not matches:
        typer.echo(c(f"\n  ✗ Session not found: {session_id}\n", RED))
        raise typer.Exit(1)

    data = json.loads(matches[0].read_text())
    print_header()
    print(f"  {c('Session:', BOLD)} {data['id']}")
    print(f"  {c('Mode:', DIM)} {data.get('mode', '?')}  "
          f"{c('Domain:', DIM)} {data.get('domain', '?')}")
    print(hr())

    for i, idea in enumerate(data.get("ideas", [])):
        print_idea(idea, i)

    if data.get("audit_trail"):
        print(f"\n  {c('Audit Trail', BOLD, DIM)}")
        for step in data["audit_trail"][-5:]:
            print(f"    {c('·', DIM)} {step.get('step', '?')}: "
                  + ", ".join(f"{k}={v}" for k, v in step.items() if k not in ("step", "ts")))
    print()


@app.command()
def status():
    """Check configuration and API key status."""
    print_header()
    print(f"  {c('Configuration Status', BOLD)}")
    print(hr())

    from dotenv import load_dotenv
    load_dotenv()

    checks = [
        ("ANTHROPIC_API_KEY", "Anthropic (Claude)", True),
        ("OPENAI_API_KEY", "OpenAI (optional)", False),
        ("SEMANTIC_SCHOLAR_API_KEY", "Semantic Scholar (optional)", False),
    ]
    for env_key, label, required in checks:
        val = os.environ.get(env_key, "")
        if val:
            masked = val[:8] + "..." + val[-4:]
            typer.echo(f"  {c('●', BGREEN)} {label:<30} {c(masked, DIM)}")
        else:
            color = RED if required else DIM
            typer.echo(f"  {c('○', color)} {label:<30} {c('not set', color)}")

    workspace = Path("workspace")
    typer.echo(f"\n  {c('Workspace:', DIM)} {workspace.absolute()}")
    if workspace.exists():
        n_sessions = len(list(workspace.glob("*/session.json")))
        typer.echo(f"  {c('Sessions:', DIM)} {n_sessions}")
    print(hr())


def main():
    app()


if __name__ == "__main__":
    main()
