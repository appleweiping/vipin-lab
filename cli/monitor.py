"""
monitor.py — Background process monitor for Vipin Lab REPL.

Spawns subprocesses, streams stdout/stderr as events, stores up to 500 events
per monitor. Non-blocking via asyncio.

Commands:
  /monitor start <cmd>
  /monitor stop <id>
  /monitor logs <id> [n]
  /monitor list
  /monitor clear
"""
from __future__ import annotations
import asyncio
import secrets
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

# ── ANSI palette ──────────────────────────────────────────────────────────────
_R = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_CYAN = "\033[36m"
_BRED = "\033[91m"
_BGREEN = "\033[92m"
_BYELLOW = "\033[93m"
_BCYAN = "\033[96m"

MAX_EVENTS = 500


@dataclass
class MonitorEvent:
    ts: float
    stream: str  # "stdout" | "stderr" | "exit"
    text: str


@dataclass
class MonitorInstance:
    id: str
    command: str
    started_at: float
    process: asyncio.subprocess.Process
    events: list[MonitorEvent] = field(default_factory=list)
    running: bool = True
    exit_code: Optional[int] = None
    _task: Optional[asyncio.Task] = field(default=None, repr=False)


# Global registry
_monitors: dict[str, MonitorInstance] = {}


def _new_id() -> str:
    return "m" + secrets.token_hex(2)  # e.g. m3f9a


def _ts_str(ts: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(ts))


async def _stream_reader(
    monitor: MonitorInstance,
    stream: asyncio.StreamReader,
    stream_name: str,
) -> None:
    """Read lines from a stream and append to monitor.events."""
    while True:
        try:
            line = await stream.readline()
        except Exception:
            break
        if not line:
            break
        text = line.decode(errors="replace").rstrip("\n\r")
        if text:
            ev = MonitorEvent(ts=time.time(), stream=stream_name, text=text)
            monitor.events.append(ev)
            if len(monitor.events) > MAX_EVENTS:
                monitor.events.pop(0)
            # Print to terminal immediately (non-blocking)
            _print_event(monitor.id, ev)


async def _monitor_task(monitor: MonitorInstance) -> None:
    """Drive stdout/stderr readers and wait for process exit."""
    tasks = []
    if monitor.process.stdout:
        tasks.append(asyncio.create_task(
            _stream_reader(monitor, monitor.process.stdout, "stdout")
        ))
    if monitor.process.stderr:
        tasks.append(asyncio.create_task(
            _stream_reader(monitor, monitor.process.stderr, "stderr")
        ))
    if tasks:
        await asyncio.gather(*tasks)
    code = await monitor.process.wait()
    monitor.exit_code = code
    monitor.running = False
    ev = MonitorEvent(ts=time.time(), stream="exit", text=f"[exited with code {code}]")
    monitor.events.append(ev)
    _print_event(monitor.id, ev)


def _print_event(monitor_id: str, ev: MonitorEvent) -> None:
    """Print a single event to stdout with ANSI formatting."""
    ts = _ts_str(ev.ts)
    if ev.stream == "stderr":
        color = _BYELLOW
    elif ev.stream == "exit":
        color = _DIM
    else:
        color = ""
    line = f"\r  {_DIM}[{monitor_id}]{_R} {_DIM}{ts}{_R}  {color}{ev.text}{_R}"
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


# ── Public API ────────────────────────────────────────────────────────────────

async def monitor_start(command: str) -> MonitorInstance:
    """Spawn a subprocess and start streaming its output."""
    mid = _new_id()
    if sys.platform == "win32":
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True,
        )
    else:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    monitor = MonitorInstance(
        id=mid,
        command=command,
        started_at=time.time(),
        process=proc,
    )
    _monitors[mid] = monitor
    task = asyncio.create_task(_monitor_task(monitor))
    monitor._task = task
    return monitor


def monitor_stop(id_prefix: str) -> str:
    """Kill a running monitor."""
    m = _find(id_prefix)
    if not m:
        return f"  {_BRED}No monitor matching: {id_prefix}{_R}"
    if m.running:
        try:
            m.process.kill()
        except Exception:
            pass
        m.running = False
    del _monitors[m.id]
    return f"  {_DIM}Monitor {m.id} stopped.{_R}"


def monitor_logs(id_prefix: str, n: int = 20) -> str:
    """Return the last n events from a monitor."""
    m = _find(id_prefix)
    if not m:
        return f"  {_BRED}No monitor matching: {id_prefix}{_R}"
    events = m.events[-n:]
    if not events:
        return f"  {_DIM}No events yet for {m.id}.{_R}"
    lines = [f"\n  {_BOLD}Monitor {m.id}{_R}  {_DIM}{m.command[:60]}{_R}"]
    for ev in events:
        ts = _ts_str(ev.ts)
        color = _BYELLOW if ev.stream == "stderr" else (_DIM if ev.stream == "exit" else "")
        lines.append(f"  {_DIM}{ts}{_R}  {color}{ev.text}{_R}")
    return "\n".join(lines) + "\n"


def monitor_list() -> str:
    """List all active monitors."""
    if not _monitors:
        return f"  {_DIM}No active monitors.{_R}"
    lines = [f"\n  {_BOLD}Monitors{_R}  {_DIM}({len(_monitors)} active){_R}"]
    for m in _monitors.values():
        status = f"{_BGREEN}running{_R}" if m.running else f"{_DIM}exited({m.exit_code}){_R}"
        elapsed = int(time.time() - m.started_at)
        lines.append(
            f"  {_BCYAN}{m.id}{_R}  {status}  {_DIM}{elapsed}s{_R}  {m.command[:50]}"
        )
    return "\n".join(lines) + "\n"


def monitor_clear() -> str:
    """Stop all monitors and clear the registry."""
    count = len(_monitors)
    for m in list(_monitors.values()):
        if m.running:
            try:
                m.process.kill()
            except Exception:
                pass
    _monitors.clear()
    return f"  {_DIM}Cleared {count} monitor(s).{_R}"


def _find(id_prefix: str) -> Optional[MonitorInstance]:
    for mid, m in _monitors.items():
        if mid.startswith(id_prefix) or mid == id_prefix:
            return m
    return None


# ── Command handler ───────────────────────────────────────────────────────────

async def handle_monitor_command(arg: str) -> str:
    """
    Parse and execute a /monitor sub-command.
    Returns a formatted string to print (or empty string if output was streamed).
    """
    parts = arg.strip().split(None, 1)
    sub = parts[0].lower() if parts else "list"
    rest = parts[1].strip() if len(parts) > 1 else ""

    if sub == "start":
        if not rest:
            return f"  {_BRED}Usage: /monitor start <command>{_R}"
        m = await monitor_start(rest)
        return (
            f"  {_BGREEN}Started{_R} monitor {_BCYAN}{m.id}{_R}  "
            f"{_DIM}{m.command[:60]}{_R}\n"
            f"  {_DIM}Events will stream to terminal. Use /monitor logs {m.id} to review.{_R}"
        )

    elif sub == "stop":
        if not rest:
            return f"  {_BRED}Usage: /monitor stop <id>{_R}"
        return monitor_stop(rest)

    elif sub == "logs":
        parts2 = rest.split(None, 1)
        mid = parts2[0] if parts2 else ""
        n = int(parts2[1]) if len(parts2) > 1 and parts2[1].isdigit() else 20
        if not mid:
            return f"  {_BRED}Usage: /monitor logs <id> [n]{_R}"
        return monitor_logs(mid, n)

    elif sub == "list":
        return monitor_list()

    elif sub == "clear":
        return monitor_clear()

    else:
        return f"  {_BRED}Usage: /monitor <start|stop|logs|list|clear> [args]{_R}"
