"""
Memory Layer — cross-session learning and institutional knowledge.

Inspired by AgentLaboratory's AgentRxiv: agents build on prior work.

Tracks:
- Which ideas survived kill-first and why
- Which ideas failed at which phase and why
- Which phenomena led to successful papers
- Which analogies were productive
- Domain-specific lessons (what works in LLM4Rec, etc.)
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class IdeaRecord:
    idea_id: str
    title: str
    domain: str
    origin: str
    phenomenon: str
    hypothesis: str
    novelty_score: float
    feasibility_score: float
    final_status: str          # killed / refined / planned / ready
    killed_at_phase: str       # which phase killed it
    kill_reason: str           # why it was killed
    paper_title: str = ""      # if it made it to paper
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class PhenomenonRecord:
    phenomenon_id: str
    domain: str
    description: str
    severity: float
    led_to_ideas: list[str]    # idea IDs generated from this phenomenon
    successful_ideas: list[str]  # ideas that made it to paper
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class DomainLesson:
    domain: str
    lesson: str                # what was learned
    evidence: str              # which idea/experiment showed this
    confidence: float          # 0-1
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class LabMemory:
    """Persistent cross-session memory for the lab."""

    def __init__(self, memory_dir: str):
        self.dir = Path(memory_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._ideas_file = self.dir / "ideas.json"
        self._phenomena_file = self.dir / "phenomena.json"
        self._lessons_file = self.dir / "lessons.json"
        self._ideas: list[IdeaRecord] = self._load(self._ideas_file)
        self._phenomena: list[PhenomenonRecord] = self._load(self._phenomena_file)
        self._lessons: list[DomainLesson] = self._load(self._lessons_file)

    # ── Write ─────────────────────────────────────────────────────────────────

    def record_idea(self, record: IdeaRecord):
        # Update if exists, else append
        for i, r in enumerate(self._ideas):
            if r.idea_id == record.idea_id:
                self._ideas[i] = record
                self._save(self._ideas_file, self._ideas)
                return
        self._ideas.append(record)
        self._save(self._ideas_file, self._ideas)

    def record_phenomenon(self, record: PhenomenonRecord):
        for i, r in enumerate(self._phenomena):
            if r.phenomenon_id == record.phenomenon_id:
                self._phenomena[i] = record
                self._save(self._phenomena_file, self._phenomena)
                return
        self._phenomena.append(record)
        self._save(self._phenomena_file, self._phenomena)

    def add_lesson(self, domain: str, lesson: str, evidence: str, confidence: float = 0.7):
        self._lessons.append(DomainLesson(
            domain=domain, lesson=lesson, evidence=evidence, confidence=confidence
        ))
        self._save(self._lessons_file, self._lessons)

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_domain_lessons(self, domain: str, min_confidence: float = 0.5) -> list[str]:
        """Get lessons relevant to a domain."""
        return [
            l.lesson for l in self._lessons
            if (domain.lower() in l.domain.lower() or l.domain.lower() in domain.lower())
            and l.confidence >= min_confidence
        ]

    def get_kill_patterns(self, domain: str) -> list[str]:
        """What types of ideas consistently get killed in this domain?"""
        killed = [
            r for r in self._ideas
            if r.final_status == "killed"
            and domain.lower() in r.domain.lower()
        ]
        if not killed:
            return []
        reasons = [r.kill_reason for r in killed if r.kill_reason]
        return reasons[:5]

    def get_successful_phenomena(self, domain: str) -> list[str]:
        """Which phenomena led to successful papers in this domain?"""
        successful = []
        for p in self._phenomena:
            if domain.lower() in p.domain.lower() and p.successful_ideas:
                successful.append(p.description)
        return successful[:5]

    def get_prior_ideas(self, domain: str, limit: int = 10) -> list[dict]:
        """Get prior ideas in this domain for context."""
        relevant = [
            r for r in self._ideas
            if domain.lower() in r.domain.lower()
        ]
        relevant.sort(key=lambda x: x.novelty_score, reverse=True)
        return [
            {
                "title": r.title,
                "hypothesis": r.hypothesis[:100],
                "status": r.final_status,
                "novelty": r.novelty_score,
            }
            for r in relevant[:limit]
        ]

    def format_context_for_prompt(self, domain: str) -> str:
        """Format memory as context for LLM prompts."""
        lines = []
        lessons = self.get_domain_lessons(domain)
        if lessons:
            lines.append(f"Domain lessons for {domain}:")
            for l in lessons[:3]:
                lines.append(f"  - {l}")

        kill_patterns = self.get_kill_patterns(domain)
        if kill_patterns:
            lines.append(f"\nIdeas that consistently fail in {domain}:")
            for k in kill_patterns[:3]:
                lines.append(f"  - {k}")

        prior = self.get_prior_ideas(domain, limit=5)
        if prior:
            lines.append(f"\nPrior ideas explored in {domain}:")
            for p in prior:
                lines.append(f"  - [{p['status']}] {p['title']}: {p['hypothesis']}")

        return "\n".join(lines) if lines else ""

    def stats(self) -> dict:
        return {
            "total_ideas": len(self._ideas),
            "survived_kill": sum(1 for r in self._ideas if r.final_status != "killed"),
            "reached_paper": sum(1 for r in self._ideas if r.final_status == "ready"),
            "total_phenomena": len(self._phenomena),
            "total_lessons": len(self._lessons),
            "domains": list({r.domain for r in self._ideas}),
        }

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self, path: Path) -> list:
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def _save(self, path: Path, data: list):
        path.write_text(
            json.dumps([d.__dict__ if hasattr(d, "__dict__") else d for d in data],
                       indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
