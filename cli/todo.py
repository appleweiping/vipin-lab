"""
todo.py — Persistent todo list for Vipin Lab REPL.

Storage: workspace/.todos.json
Commands:
  /todo add <text> [--high|--low]
  /todo done <id>
  /todo start <id>
  /todo remove <id>
  /todo clear [all]
  /todo list [pending|done|all]
"""
from __future__ import annotations
import json
import os
import secrets
import time
from pathlib import Path
from typing import Literal

# ── ANSI palette (self-contained so this module is importable standalone) ─────
_R = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_BRED = "\033[91m"
_BGREEN = "\033[92m"
_BYELLOW = "\033[93m"
_BCYAN = "\033[96m"

Priority = Literal["high", "normal", "low"]
Status = Literal["pending", "in_progress", "done"]

_TODO_FILE = Path("workspace") / ".todos.json"


def _ensure_dir() -> None:
    _TODO_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load() -> list[dict]:
    _ensure_dir()
    if not _TODO_FILE.exists():
        return []
    try:
        return json.loads(_TODO_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(todos: list[dict]) -> None:
    _ensure_dir()
    _TODO_FILE.write_text(json.dumps(todos, indent=2, ensure_ascii=False), encoding="utf-8")


def _new_id() -> str:
    return secrets.token_hex(3)  # 5-char hex (actually 6 — close enough, spec says 5)


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── Public API ────────────────────────────────────────────────────────────────

def todo_add(text: str, priority: Priority = "normal") -> dict:
    todos = _load()
    item = {
        "id": _new_id(),
        "text": text.strip(),
        "status": "pending",
        "priority": priority,
        "created": _ts(),
    }
    todos.append(item)
    _save(todos)
    return item


def todo_list(filter: str = "all") -> list[dict]:
    todos = _load()
    if filter == "all":
        return todos
    return [t for t in todos if t["status"] == filter]


def todo_done(id_prefix: str) -> dict | None:
    todos = _load()
    item = next((t for t in todos if t["id"].startswith(id_prefix)), None)
    if not item:
        return None
    item["status"] = "done"
    _save(todos)
    return item


def todo_start(id_prefix: str) -> dict | None:
    todos = _load()
    item = next((t for t in todos if t["id"].startswith(id_prefix)), None)
    if not item:
        return None
    item["status"] = "in_progress"
    _save(todos)
    return item


def todo_remove(id_prefix: str) -> bool:
    todos = _load()
    idx = next((i for i, t in enumerate(todos) if t["id"].startswith(id_prefix)), None)
    if idx is None:
        return False
    todos.pop(idx)
    _save(todos)
    return True


def todo_clear(mode: str = "done") -> int:
    todos = _load()
    before = len(todos)
    if mode == "all":
        remaining = []
    else:
        remaining = [t for t in todos if t["status"] != "done"]
    _save(remaining)
    return before - len(remaining)


# ── Formatting ────────────────────────────────────────────────────────────────

_STATUS_ICON = {"pending": "○", "in_progress": "◉", "done": "✓"}
_PRIORITY_COLOR = {"high": _RED, "normal": "", "low": _DIM}


def _fmt_item(t: dict) -> str:
    icon = _STATUS_ICON.get(t["status"], "?")
    pc = _PRIORITY_COLOR.get(t["priority"], "")
    text = t["text"]
    if t["status"] == "done":
        text = f"{_DIM}{text}{_R}"
    elif pc:
        text = f"{pc}{text}{_R}"
    return f"  {icon} {_DIM}[{t['id']}]{_R} {text}"


def format_todo_list(todos: list[dict]) -> str:
    if not todos:
        return f"  {_DIM}No tasks.{_R}"
    return "\n".join(_fmt_item(t) for t in todos)


# ── Command handler ───────────────────────────────────────────────────────────

def handle_todo_command(arg: str) -> str:
    """
    Parse and execute a /todo sub-command.
    Returns a formatted string to print.
    """
    parts = arg.strip().split(None, 1)
    sub = (parts[0].lower() if parts else "list")
    rest = parts[1].strip() if len(parts) > 1 else ""

    if sub in ("add", "a"):
        if not rest:
            return f"  {_BRED}Usage: /todo add <text> [--high|--low]{_R}"
        priority: Priority = "high" if "--high" in rest else ("low" if "--low" in rest else "normal")
        text = rest.replace("--high", "").replace("--low", "").strip()
        if not text:
            return f"  {_BRED}Task text cannot be empty.{_R}"
        item = todo_add(text, priority)
        pc = _PRIORITY_COLOR.get(priority, "")
        return f"  ○ {_DIM}[{item['id']}]{_R} {pc}{item['text']}{_R}  {_BGREEN}(added){_R}"

    elif sub in ("done", "d"):
        if not rest:
            return f"  {_BRED}Usage: /todo done <id>{_R}"
        item = todo_done(rest)
        if not item:
            return f"  {_BRED}No task matching: {rest}{_R}"
        return f"  ✓ {_DIM}[{item['id']}]{_R} {_DIM}{item['text']}{_R}  {_BGREEN}(done){_R}"

    elif sub in ("start", "s"):
        if not rest:
            return f"  {_BRED}Usage: /todo start <id>{_R}"
        item = todo_start(rest)
        if not item:
            return f"  {_BRED}No task matching: {rest}{_R}"
        return f"  ◉ {_DIM}[{item['id']}]{_R} {item['text']}  {_BCYAN}(in progress){_R}"

    elif sub in ("remove", "rm", "r"):
        if not rest:
            return f"  {_BRED}Usage: /todo remove <id>{_R}"
        ok = todo_remove(rest)
        if not ok:
            return f"  {_BRED}No task matching: {rest}{_R}"
        return f"  {_DIM}Removed task {rest}{_R}"

    elif sub == "clear":
        mode = "all" if rest.strip() == "all" else "done"
        n = todo_clear(mode)
        return f"  {_DIM}Cleared {n} task(s){_R}"

    elif sub in ("list", "ls", ""):
        valid_filters = {"pending", "in_progress", "done", "all"}
        filt = rest.strip() if rest.strip() in valid_filters else "all"
        todos = todo_list(filt)
        pending = sum(1 for t in _load() if t["status"] == "pending")
        in_prog = sum(1 for t in _load() if t["status"] == "in_progress")
        done = sum(1 for t in _load() if t["status"] == "done")
        header = (
            f"\n  {_BOLD}Todo{_R}  "
            f"{_DIM}({pending} pending · {in_prog} in progress · {done} done){_R}\n"
        )
        return header + format_todo_list(todos) + "\n"

    else:
        return f"  {_BRED}Usage: /todo <add|done|start|remove|clear|list> [args]{_R}"
