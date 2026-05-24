"""
vlab REPL — Natural language interactive mode.

Type anything. The system understands intent.
No need to remember command syntax.

Examples:
  "find new research directions in LLM4Rec"
  "extend my conformal prediction project"
  "transfer ideas from NLP to recommendation"
  "run the pipeline on idea abc123"
  "show me all my ideas"

Slash commands for power users:
  /discover <domain>
  /extend <domain>
  /transfer <source> <target>
  /pipeline <id>
  /resume <id>
  /ideas
  /sessions
  /status
  /help
  /clear
  /quit
"""
from __future__ import annotations
import asyncio
import json
import os
import re
import sys
import shutil
import textwrap
import time
import threading
import itertools
import readline as _rl  # enables history + line editing on Unix
from pathlib import Path
from typing import Callable, Awaitable

# ── ANSI palette ──────────────────────────────────────────────────────────────
R = "\033[0m"; BOLD = "\033[1m"; DIM = "\033[2m"; ITALIC = "\033[3m"
RED = "\033[31m"; GREEN = "\033[32m"; YELLOW = "\033[33m"
BLUE = "\033[34m"; MAGENTA = "\033[35m"; CYAN = "\033[36m"
BRED = "\033[91m"; BGREEN = "\033[92m"; BYELLOW = "\033[93m"
BBLUE = "\033[94m"; BMAGENTA = "\033[95m"; BCYAN = "\033[96m"; BWHITE = "\033[97m"

def c(*args):
    codes = [a for a in args if isinstance(a, str) and a.startswith("\033")]
    texts = [a for a in args if not (isinstance(a, str) and a.startswith("\033"))]
    return "".join(codes) + str(texts[0] if texts else "") + R

def hr(char="─", width=None):
    w = width or min(shutil.get_terminal_size().columns, 90)
    return c(char * w, DIM)

def wrap(text: str, indent: str = "  ", width: int = None) -> str:
    w = width or min(shutil.get_terminal_size().columns - 4, 86)
    lines = []
    for para in str(text).split("\n"):
        if not para.strip():
            lines.append("")
        else:
            lines.extend(textwrap.wrap(para, w, initial_indent=indent,
                                       subsequent_indent=indent))
    return "\n".join(lines)


# ── Spinner ───────────────────────────────────────────────────────────────────
class Spinner:
    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, msg: str = "", color: str = BCYAN):
        self.msg = msg
        self.color = color
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t0 = 0.0
        self._sub = ""  # sub-step message

    def update(self, sub: str):
        self._sub = sub

    def _run(self):
        for f in itertools.cycle(self.FRAMES):
            if self._stop.is_set():
                break
            elapsed = time.time() - self._t0
            sub = f"  {c(self._sub[:50], DIM)}" if self._sub else ""
            line = f"\r  {c(f, self.color)} {self.msg}{sub}  {c(f'{elapsed:.0f}s', DIM)}  "
            sys.stdout.write(line)
            sys.stdout.flush()
            time.sleep(0.08)
        sys.stdout.write("\r" + " " * 80 + "\r")
        sys.stdout.flush()

    def __enter__(self):
        self._t0 = time.time()
        self._t.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._t.join()


# ── Intent parser ─────────────────────────────────────────────────────────────
class IntentParser:
    """
    Parses natural language input into structured commands.
    No LLM needed — fast regex + keyword matching.
    """

    PATTERNS = [
        # discover / find / scan
        (r"(?:discover|find|scan|explore|search|look for|identify)\s+(?:new\s+)?(?:ideas?|directions?|research|phenomena?|topics?)\s+(?:in|for|about|on)\s+(.+)",
         "discover", 1),
        (r"(?:what(?:'s| is) new in|latest in|trends? in)\s+(.+)",
         "discover", 1),
        (r"(?:discover|scan)\s+(.+)",
         "discover", 1),

        # extend / follow-up
        (r"(?:extend|follow.?up|build on|continue|next steps? for)\s+(?:my\s+)?(.+?)(?:\s+project)?$",
         "extend", 1),

        # transfer
        (r"(?:transfer|apply|port|adapt|move)\s+(?:ideas?|methods?|techniques?|approaches?)\s+from\s+(.+?)\s+to\s+(.+)",
         "transfer", (1, 2)),
        (r"(?:how would|can we apply)\s+(.+?)\s+(?:to|in)\s+(.+)",
         "transfer", (1, 2)),

        # pipeline
        (r"(?:run|start|execute|launch)\s+(?:the\s+)?(?:full\s+)?pipeline\s+(?:on|for)\s+([a-f0-9]{6,})",
         "pipeline", 1),
        (r"(?:run|process)\s+idea\s+([a-f0-9]{6,})",
         "pipeline", 1),

        # resume
        (r"(?:resume|continue|restart)\s+(?:pipeline\s+)?(?:for\s+)?([a-f0-9]{6,})",
         "resume", 1),

        # list ideas
        (r"(?:show|list|display|what are)\s+(?:my\s+)?(?:all\s+)?ideas?",
         "ideas", None),
        (r"(?:show|list)\s+ideas?\s+(?:in|for|about)\s+(.+)",
         "ideas_domain", 1),

        # sessions
        (r"(?:show|list|display)\s+(?:recent\s+)?sessions?",
         "sessions", None),

        # status
        (r"(?:check|show|display)\s+(?:my\s+)?(?:config|status|setup|keys?)",
         "status", None),

        # help
        (r"(?:help|what can you do|commands?|how do i)",
         "help", None),
    ]

    def parse(self, text: str) -> tuple[str, dict]:
        """Returns (intent, args_dict)."""
        text = text.strip()

        # Slash commands take priority
        if text.startswith("/") or text.startswith("\\"):
            return self._parse_slash(text[1:])

        text_lower = text.lower()
        for pattern, intent, groups in self.PATTERNS:
            m = re.search(pattern, text_lower, re.IGNORECASE)
            if m:
                if groups is None:
                    return intent, {}
                elif isinstance(groups, int):
                    # Try to get the original-case version
                    start = m.start(groups)
                    end = m.end(groups)
                    original = text[start:end] if start < len(text) else m.group(groups)
                    return intent, {"arg1": original.strip()}
                else:
                    g1, g2 = groups
                    return intent, {
                        "arg1": text[m.start(g1):m.end(g1)].strip(),
                        "arg2": text[m.start(g2):m.end(g2)].strip(),
                    }

        # Fallback: treat as domain discovery if it looks like a domain name
        if len(text.split()) <= 5 and not any(
            w in text_lower for w in ["what", "how", "why", "when", "where", "who"]
        ):
            return "discover", {"arg1": text}

        return "unknown", {"raw": text}

    def _parse_slash(self, cmd: str) -> tuple[str, dict]:
        parts = cmd.strip().split(None, 2)
        if not parts:
            return "help", {}
        name = parts[0].lower()
        mapping = {
            "discover": ("discover", {"arg1": parts[1] if len(parts) > 1 else ""}),
            "extend":   ("extend",   {"arg1": parts[1] if len(parts) > 1 else ""}),
            "transfer": ("transfer", {"arg1": parts[1] if len(parts) > 1 else "",
                                      "arg2": parts[2] if len(parts) > 2 else ""}),
            "pipeline": ("pipeline", {"arg1": parts[1] if len(parts) > 1 else ""}),
            "resume":   ("resume",   {"arg1": parts[1] if len(parts) > 1 else ""}),
            "ideas":    ("ideas",    {}),
            "sessions": ("sessions", {}),
            "status":   ("status",   {}),
            "help":     ("help",     {}),
            "clear":    ("clear",    {}),
            "quit":     ("quit",     {}),
            "exit":     ("quit",     {}),
            "q":        ("quit",     {}),
        }
        return mapping.get(name, ("unknown", {"raw": cmd}))


# ── Output helpers ────────────────────────────────────────────────────────────
def print_banner():
    cols = shutil.get_terminal_size().columns
    print()
    print(f"  {c('⚗', BMAGENTA)} {c('Vipin Lab', BOLD, BMAGENTA)}  {c('v1.3', DIM)}")
    print(c("  Autonomous Research System — Phenomenon-Driven Discovery", DIM))
    print(hr())
    print(f"  {c('Type your research question or use /help for commands.', DIM)}")
    print(f"  {c('Examples:', DIM)}  {c('find new ideas in LLM4Rec', ITALIC, DIM)}  ·  "
          f"{c('transfer conformal prediction to recommendation', ITALIC, DIM)}")
    print()


def print_idea_card(idea: dict, index: int = 0):
    status = idea.get("status", "?")
    origin = idea.get("origin", "?")
    status_colors = {
        "kill_tested": BYELLOW, "refined": BGREEN, "planned": BCYAN,
        "running": BCYAN, "ready": BGREEN, "killed": RED, "generated": DIM,
    }
    origin_icons = {"phenomenon": "🔬", "extension": "🔗", "transfer": "⚡",
                    "literature": "📚", "serendipity": "✨"}
    sc = status_colors.get(status, DIM)
    icon = origin_icons.get(origin, "💡")

    print(f"\n  {c(f'#{index+1}', DIM)} {icon}  {c(idea.get('title', 'Untitled'), BOLD)}")
    print(f"     {c(status, sc)}  "
          f"{c('N:', DIM)}{c(f\"{idea.get('novelty_score', 0):.1f}\", BYELLOW)}  "
          f"{c('F:', DIM)}{c(f\"{idea.get('feasibility_score', 0):.1f}\", BGREEN)}  "
          f"{c(idea.get('id', '')[:8], DIM)}")
    if idea.get("phenomenon"):
        print(f"     {c('↳', DIM)} {wrap(idea['phenomenon'][:100], indent='').strip()}")
    kill = idea.get("kill_survived")
    if kill is not None:
        sym = c("✓ survived kill-first", BGREEN) if kill else c("✗ killed", RED)
        print(f"     {sym}")


def print_session_result(session):
    ideas = session.ideas if hasattr(session, "ideas") else []
    phenomena = session.phenomena if hasattr(session, "phenomena") else []
    analogies = getattr(session, "analogies", [])

    print(f"\n  {c('Session', BOLD, DIM)} {c(session.id, DIM)}")
    print(hr("·"))

    if phenomena:
        print(f"\n  {c('Phenomena detected', BOLD, BYELLOW)} {c(f'({len(phenomena)})', DIM)}")
        for i, p in enumerate(phenomena[:3]):
            sev = int(p.severity * 10)
            bar = c("█" * sev, BYELLOW) + c("░" * (10 - sev), DIM)
            print(f"  {c(f'P{i+1}', BYELLOW)} {bar}  {p.description[:80]}")

    if analogies:
        print(f"\n  {c('Analogies found', BOLD, BCYAN)} {c(f'({len(analogies)})', DIM)}")
        for a in analogies[:3]:
            conf = int(a.confidence * 100)
            print(f"  {c('⚡', BCYAN)} {c(f'{conf}%', BCYAN)}  {a.target_problem[:70]}")

    surviving = [i for i in ideas if i.status.value == "kill_tested"]
    killed = [i for i in ideas if i.status.value == "killed"]

    print(f"\n  {c('Ideas', BOLD, BCYAN)} {c(f'{len(surviving)} survived · {len(killed)} killed', DIM)}")
    for idx, idea in enumerate(ideas):
        idea_dict = {
            "title": idea.title, "status": idea.status.value,
            "origin": idea.origin.value, "novelty_score": idea.novelty_score,
            "feasibility_score": idea.feasibility_score,
            "phenomenon": idea.phenomenon, "id": idea.id,
            "kill_survived": idea.kill_argument.survived if idea.kill_argument else None,
        }
        print_idea_card(idea_dict, idx)

    if surviving:
        best = max(surviving, key=lambda i: i.novelty_score + i.feasibility_score)
        print(f"\n  {c('→ Next step:', BOLD, BGREEN)} "
              f"{c(f'vlab pipeline {best.id[:8]}', BCYAN)}")
    print()


HELP_TEXT = f"""
  {c('Vipin Lab — Natural Language Commands', BOLD)}
  {hr('─', 60)}

  {c('Discovery', BOLD, BYELLOW)}
  {c('find new ideas in LLM4Rec', CYAN)}
  {c('discover research directions in uncertainty quantification', CYAN)}
  {c('what is new in conformal prediction', CYAN)}

  {c('Extension', BOLD, BYELLOW)}
  {c('extend my conformal prediction project', CYAN)}
  {c('follow-up ideas for TGL-Rec', CYAN)}

  {c('Cross-Domain Transfer', BOLD, BYELLOW)}
  {c('transfer ideas from NLP to recommendation', CYAN)}
  {c('apply conformal prediction to LLM4Rec', CYAN)}

  {c('Pipeline', BOLD, BYELLOW)}
  {c('run pipeline on idea abc12345', CYAN)}
  {c('resume abc12345', CYAN)}

  {c('Slash Commands', BOLD, BYELLOW)}
  {c('/discover <domain>', CYAN)}   {c('/extend <domain>', CYAN)}   {c('/transfer <src> <tgt>', CYAN)}
  {c('/pipeline <id>', CYAN)}       {c('/resume <id>', CYAN)}       {c('/ideas', CYAN)}
  {c('/sessions', CYAN)}            {c('/status', CYAN)}            {c('/clear', CYAN)}   {c('/quit', CYAN)}

  {c('Tips', BOLD, DIM)}
  · Enter to send · Ctrl+C to cancel · ↑↓ for history
"""


# ── REPL ──────────────────────────────────────────────────────────────────────
class VlabREPL:
    def __init__(self):
        self.parser = IntentParser()
        self.orchestrator = None
        self._history: list[str] = []
        self._setup_readline()

    def _setup_readline(self):
        """Configure readline for history and completion."""
        try:
            history_file = Path.home() / ".vlab_history"
            if history_file.exists():
                _rl.read_history_file(str(history_file))
            _rl.set_history_length(500)

            # Tab completion for slash commands
            slash_cmds = ["/discover", "/extend", "/transfer", "/pipeline",
                          "/resume", "/ideas", "/sessions", "/status",
                          "/help", "/clear", "/quit"]

            def completer(text, state):
                options = [c for c in slash_cmds if c.startswith(text)]
                return options[state] if state < len(options) else None

            _rl.set_completer(completer)
            _rl.parse_and_bind("tab: complete")
        except Exception:
            pass  # readline not available on all platforms

    def _save_history(self):
        try:
            _rl.write_history_file(str(Path.home() / ".vlab_history"))
        except Exception:
            pass

    def _get_orchestrator(self):
        if self.orchestrator is not None:
            return self.orchestrator
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from lab.core.config import LabConfig
            from lab.core.orchestrator import LabOrchestrator
            config = LabConfig()
            if not config.anthropic_key:
                print(c("\n  ✗ ANTHROPIC_API_KEY not set. Add it to .env\n", BRED))
                return None
            self.orchestrator = LabOrchestrator(config)
            return self.orchestrator
        except ImportError as e:
            print(c(f"\n  ✗ Import error: {e}\n  Run: pip install -e .\n", BRED))
            return None

    def _prompt(self) -> str:
        """Render the input prompt."""
        return f"  {c('⚗', BMAGENTA)} {c('›', BOLD, DIM)} "

    async def _handle_discover(self, args: dict):
        domain = args.get("arg1", "").strip()
        if not domain:
            domain = input(f"  {c('Domain:', DIM)} ").strip()
        if not domain:
            return
        orch = self._get_orchestrator()
        if not orch:
            return
        print(f"\n  {c('🔬 Discovering phenomena in', DIM)} {c(domain, BOLD)}")
        print(hr("·"))
        with Spinner(f"Scanning {domain}", BMAGENTA) as sp:
            sp.update("querying Semantic Scholar...")
            session = await orch.discover(domain)
        print_session_result(session)

    async def _handle_extend(self, args: dict):
        domain = args.get("arg1", "").strip()
        if not domain:
            domain = input(f"  {c('Domain:', DIM)} ").strip()
        method = input(f"  {c('Current method:', DIM)} ").strip()
        results = input(f"  {c('Current results (optional):', DIM)} ").strip()
        limits = input(f"  {c('Known limitations (optional):', DIM)} ").strip()
        if not domain or not method:
            print(c("  Domain and method are required.\n", BRED))
            return
        orch = self._get_orchestrator()
        if not orch:
            return
        print(f"\n  {c('🔗 Generating extension ideas for', DIM)} {c(domain, BOLD)}")
        print(hr("·"))
        with Spinner("Generating extension ideas", BMAGENTA):
            session = await orch.extend(domain, method, results, limits)
        print_session_result(session)

    async def _handle_transfer(self, args: dict):
        source = args.get("arg1", "").strip()
        target = args.get("arg2", "").strip()
        if not source:
            source = input(f"  {c('Source domain:', DIM)} ").strip()
        if not target:
            target = input(f"  {c('Target domain:', DIM)} ").strip()
        if not source or not target:
            print(c("  Both source and target domains are required.\n", BRED))
            return
        orch = self._get_orchestrator()
        if not orch:
            return
        print(f"\n  {c('⚡ Transferring', DIM)} {c(source, BOLD)} {c('→', DIM)} {c(target, BOLD)}")
        print(hr("·"))
        with Spinner(f"Finding analogies: {source} → {target}", BMAGENTA):
            session = await orch.transfer(source, target)
        print_session_result(session)

    async def _handle_pipeline(self, args: dict):
        idea_id = args.get("arg1", "").strip()
        if not idea_id:
            idea_id = input(f"  {c('Idea ID:', DIM)} ").strip()
        if not idea_id:
            return
        orch = self._get_orchestrator()
        if not orch:
            return
        idea = orch.workspace.load_idea(idea_id)
        if not idea:
            print(c(f"\n  ✗ Idea not found: {idea_id}\n", BRED))
            return
        stage = orch.workspace.get_pipeline_stage(idea)
        print(f"\n  {c('🔬 Pipeline', DIM)} {c(idea.title[:60], BOLD)}")
        print(f"  {c('Stage:', DIM)} {c(stage, BYELLOW)}  {c('Status:', DIM)} {c(idea.status.value, BCYAN)}")
        print(hr("·"))
        if stage == "bridge_done":
            print(f"  {c('⚠ Waiting for experiments.', BYELLOW)}")
            print(f"  Place results in: {c(idea.workspace_dir + '/experiments/results/', DIM)}")
            print(f"  Then type: {c('resume ' + idea_id[:8], BCYAN)}\n")
            return
        with Spinner("Running pipeline", BMAGENTA) as sp:
            sp.update(f"stage: {stage}")
            result_idea, paper = await orch.run_pipeline(idea)
        if paper:
            print(f"\n  {c('✓ Paper ready', BGREEN)}")
            print(f"  {c('Title:', DIM)} {c(paper.title, BOLD)}")
            scores = paper.review_scores
            if scores:
                print(f"  {c('Review scores:', DIM)} " +
                      "  ".join(f"{k}: {c(str(int(v)), BGREEN if v >= 7 else BYELLOW)}"
                                for k, v in scores.items()))
        else:
            print(f"\n  {c('Status:', DIM)} {c(result_idea.status.value, BYELLOW)}")
        print()

    async def _handle_resume(self, args: dict):
        idea_id = args.get("arg1", "").strip()
        if not idea_id:
            idea_id = input(f"  {c('Idea ID:', DIM)} ").strip()
        if not idea_id:
            return
        orch = self._get_orchestrator()
        if not orch:
            return
        print(f"\n  {c('↩ Resuming pipeline:', DIM)} {c(idea_id, BOLD)}")
        print(hr("·"))
        with Spinner("Resuming", BMAGENTA):
            idea, paper = await orch.resume_pipeline(idea_id)
        if idea is None:
            print(c(f"\n  ✗ Idea not found: {idea_id}\n", BRED))
            return
        print(f"\n  {c('Status:', DIM)} {c(idea.status.value, BGREEN)}")
        if paper:
            print(f"  {c('Paper:', DIM)} {c(paper.title, BOLD)}")
        print()

    def _handle_ideas(self, args: dict):
        orch = self._get_orchestrator()
        if not orch:
            return
        domain = args.get("arg1", "")
        all_ideas = orch.workspace.list_ideas()
        if domain:
            all_ideas = [i for i in all_ideas if domain.lower() in i.get("domain", "").lower()]
        if not all_ideas:
            print(c("\n  No ideas found.\n", DIM))
            return
        print(f"\n  {c('Ideas', BOLD)}  {c(f'({len(all_ideas)} total)', DIM)}")
        print(hr("·"))
        for idx, idea in enumerate(all_ideas[:20]):
            print_idea_card(idea, idx)
            print(f"     {c('stage:', DIM)} {c(idea.get('stage', '?'), BCYAN)}")
        print()

    def _handle_sessions(self):
        workspace = Path("workspace")
        if not workspace.exists():
            print(c("\n  No sessions yet.\n", DIM))
            return
        files = sorted(workspace.glob("*/session.json"), reverse=True)[:15]
        if not files:
            print(c("\n  No sessions found.\n", DIM))
            return
        print(f"\n  {c('Recent Sessions', BOLD)}")
        print(hr("·"))
        for f in files:
            try:
                d = json.loads(f.read_text())
                ts = d.get("created_at", "")[:16].replace("T", " ")
                mode_icons = {"discover": "🔬", "extend": "🔗", "transfer": "⚡"}
                icon = mode_icons.get(d.get("mode", ""), "💡")
                n = len(d.get("ideas", []))
                surv = sum(1 for i in d.get("ideas", []) if i.get("kill_survived"))
                print(f"  {c(d['id'], DIM)}  {c(ts, DIM)}  {icon} "
                      f"{c(d.get('domain', '?')[:28], BOLD)}  "
                      f"{c(f'{surv}/{n}', BGREEN)}")
            except Exception:
                pass
        print()

    def _handle_status(self):
        from dotenv import load_dotenv
        load_dotenv()
        print(f"\n  {c('Configuration', BOLD)}")
        print(hr("·"))
        checks = [
            ("ANTHROPIC_API_KEY", "Anthropic (Claude)", True),
            ("OPENAI_API_KEY", "OpenAI", False),
            ("SEMANTIC_SCHOLAR_API_KEY", "Semantic Scholar", False),
        ]
        for key, label, required in checks:
            val = os.environ.get(key, "")
            if val:
                masked = val[:8] + "…" + val[-4:]
                print(f"  {c('●', BGREEN)} {label:<28} {c(masked, DIM)}")
            else:
                col = BRED if required else DIM
                print(f"  {c('○', col)} {label:<28} {c('not set', col)}")
        ws = Path("workspace")
        n = len(list(ws.glob("*/session.json"))) if ws.exists() else 0
        print(f"\n  {c('Workspace:', DIM)} {ws.absolute()}")
        print(f"  {c('Sessions:', DIM)} {n}")
        print()

    async def _dispatch(self, intent: str, args: dict):
        """Route intent to handler."""
        if intent == "discover":
            await self._handle_discover(args)
        elif intent == "extend":
            await self._handle_extend(args)
        elif intent == "transfer":
            await self._handle_transfer(args)
        elif intent == "pipeline":
            await self._handle_pipeline(args)
        elif intent == "resume":
            await self._handle_resume(args)
        elif intent in ("ideas", "ideas_domain"):
            self._handle_ideas(args)
        elif intent == "sessions":
            self._handle_sessions()
        elif intent == "status":
            self._handle_status()
        elif intent == "help":
            print(HELP_TEXT)
        elif intent == "clear":
            os.system("cls" if os.name == "nt" else "clear")
            print_banner()
        elif intent == "quit":
            raise KeyboardInterrupt
        else:
            raw = args.get("raw", "")
            print(f"\n  {c('?', BYELLOW)} I didn't understand: {c(raw[:60], DIM)}")
            print(f"  Try: {c('find new ideas in <domain>', CYAN)} or {c('/help', CYAN)}\n")

    async def run(self):
        """Main REPL loop."""
        print_banner()

        while True:
            try:
                line = input(self._prompt()).strip()
            except (EOFError, KeyboardInterrupt):
                print(f"\n  {c('Goodbye.', DIM)}\n")
                self._save_history()
                break

            if not line:
                continue

            intent, args = self.parser.parse(line)

            try:
                await self._dispatch(intent, args)
            except KeyboardInterrupt:
                print(f"\n  {c('Goodbye.', DIM)}\n")
                self._save_history()
                break
            except Exception as e:
                print(c(f"\n  ✗ Error: {e}\n", BRED))


def run_repl():
    """Entry point for the REPL."""
    repl = VlabREPL()
    asyncio.run(repl.run())


if __name__ == "__main__":
    run_repl()
