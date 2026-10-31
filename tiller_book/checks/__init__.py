"""Run checks and aggregate them fail-closed: only an all-PASS set of required checks passes."""

import shlex
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    name: str
    command: tuple
    tools: tuple = ()
    timeout: float = 600
    required: bool = True


def run_check(check, cwd="."):
    """Return a dict shaped like a receipt checks[] item."""
    result = {"name": check.name, "command": shlex.join(check.command)}
    missing = [t for t in check.tools if shutil.which(t) is None]
    if missing:
        return {**result, "status": "NOT_RUN", "exit_code": None, "reason": f"tool not on PATH: {', '.join(missing)}"}
    try:
        p = subprocess.run(list(check.command), cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=check.timeout)
    except subprocess.TimeoutExpired:
        return {**result, "status": "NOT_RUN", "exit_code": None, "reason": f"timed out after {check.timeout} s"}
    except OSError as e:
        return {**result, "status": "NOT_RUN", "exit_code": None, "reason": f"could not start: {e}"}
    if p.returncode == 0:
        return {**result, "status": "PASS", "exit_code": 0}
    lines = [line.strip() for line in (p.stdout + "\n" + p.stderr).splitlines() if line.strip()]
    last = lines[-1] if lines else "no output"
    return {**result, "status": "FAIL", "exit_code": p.returncode, "reason": f"exit {p.returncode}: {last}"}


def aggregate(checks, results):
    """Return (exit code, verdict line). Exit 0 only if at least one required check ran and all required checks PASS."""
    required = [r for c, r in zip(checks, results) if c.required]
    if not required:
        return 1, "FAIL: no required checks, nothing was checked"
    bad = [r["name"] for r in required if r["status"] != "PASS"]
    if bad:
        return 1, f"FAIL: required checks not PASS: {', '.join(bad)}"
    return 0, f"PASS: all {len(required)} required checks passed"


def line(check, result):
    tag = "" if check.required else " (optional)"
    return f"{result['status']} {result['name']}{tag}: {result.get('reason', 'exit 0')}"
