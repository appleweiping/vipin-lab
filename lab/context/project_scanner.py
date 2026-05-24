"""Project context scanner — reads shared memory to inject active project state."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path

_MEMORY_ROOT = Path(r"D:\research\Vipin's Knowledgebase\memory")
_MAILBOX_ROOT = Path(r"D:\devtools\agent-hub\state")


@dataclass
class ActiveProject:
    name: str
    direction: str
    status: str
    phase: str
    priority: int


@dataclass
class ProjectContext:
    projects: list[ActiveProject] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    raw_summary: str = ""

    def as_prompt_block(self) -> str:
        if not self.projects and not self.rules:
            return ""
        lines = ["=== Active Research Projects ==="]
        for p in self.projects:
            lines.append(f"[P{p.priority}] {p.name}: {p.direction} | Status: {p.status}")
        if self.rules:
            lines.append("\n=== Key Rules ===")
            lines.extend(f"- {r}" for r in self.rules[:5])
        return "\n".join(lines)

    def find_project(self, query: str) -> ActiveProject | None:
        q = query.lower()
        for p in self.projects:
            if p.name.lower() in q or any(w in q for w in p.name.lower().split()):
                return p
        return None


def load_project_context() -> ProjectContext:
    """Read shared memory and return structured project context."""
    ctx = ProjectContext()
    _load_projects(ctx)
    _load_rules(ctx)
    return ctx


def _load_projects(ctx: ProjectContext) -> None:
    status_file = _MEMORY_ROOT / "facts" / "all-projects-status.md"
    if not status_file.exists():
        return
    try:
        text = status_file.read_text(encoding="utf-8", errors="replace")
        ctx.raw_summary = text[:2000]
        # Parse markdown table rows: | # | project | direction | status | server |
        for m in re.finditer(
            r'\|\s*(\d+)\s*\|\s*\*\*([^*]+)\*\*\s*\|\s*([^|]+)\|\s*([^|]+)\|',
            text
        ):
            priority = int(m.group(1))
            name = m.group(2).strip()
            direction = m.group(3).strip()
            status_raw = m.group(4).strip()
            # Extract phase from status (e.g. "experiment-bridge", "Phase 10")
            phase_m = re.search(r'(Phase \d+|experiment-\w+|research-\w+|paper-\w+|Gate \w+)', status_raw)
            phase = phase_m.group(1) if phase_m else status_raw[:40]
            ctx.projects.append(ActiveProject(
                name=name, direction=direction,
                status=status_raw[:80], phase=phase, priority=priority
            ))
    except Exception:
        pass


def _load_rules(ctx: ProjectContext) -> None:
    rules_file = _MEMORY_ROOT / "decisions" / "research-hard-rules.md"
    if not rules_file.exists():
        return
    try:
        text = rules_file.read_text(encoding="utf-8", errors="replace")
        # Extract bullet points
        for m in re.finditer(r'^[-*]\s+(.+)$', text, re.MULTILINE):
            rule = m.group(1).strip()
            if len(rule) > 20:
                ctx.rules.append(rule)
                if len(ctx.rules) >= 8:
                    break
    except Exception:
        pass


def read_mailbox(agent: str) -> list[dict]:
    """Read unread messages from agent mailbox."""
    import json
    mailbox_file = _MAILBOX_ROOT / f"messages-{agent}.json"
    if not mailbox_file.exists():
        return []
    try:
        data = json.loads(mailbox_file.read_text(encoding="utf-8"))
        return [m for m in data.get("messages", []) if not m.get("read", False)]
    except Exception:
        return []


def mark_messages_read(agent: str) -> None:
    """Mark all messages in mailbox as read."""
    import json
    mailbox_file = _MAILBOX_ROOT / f"messages-{agent}.json"
    if not mailbox_file.exists():
        return
    try:
        data = json.loads(mailbox_file.read_text(encoding="utf-8"))
        for m in data.get("messages", []):
            m["read"] = True
        mailbox_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
