"""Isolated replay: copy a scenario workspace, apply a reviewed repair, run the agent and
its acceptance checks, then throw the copy away. The original scenario files are never
modified.

Two isolation levels:
- "subprocess" (default): a temp copy, `python -E -s` (no user site, PYTHON* env vars ignored),
  a stripped environment without API keys, and a wall-clock timeout.
- "docker": the same copy mounted into a throwaway container with no network,
  a read-only root filesystem, and CPU/memory/PID limits.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .scenarios import ROOT as SCENARIO_ROOT
from .scenarios import Scenario
from .schema import AcceptanceCheck, FileEdit, SandboxRun, Trace

MAX_FILE_BYTES = 20_000
BANNED_IMPORTS = {
    "os", "sys", "subprocess", "socket", "shutil", "ctypes", "importlib", "pathlib",
    "multiprocessing", "threading", "urllib", "http", "requests", "httpx", "pickle", "builtins",
}
BANNED_CALLS = {"eval", "exec", "compile", "open", "__import__", "globals", "locals", "getattr", "setattr"}


class RepairRejected(ValueError):
    pass


def check_code_safety(source: str, filename: str) -> None:
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        raise RepairRejected(f"{filename}: syntax error after edit: {exc.msg} (line {exc.lineno})")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for name in names:
                if name.split(".")[0] in BANNED_IMPORTS:
                    raise RepairRejected(f"{filename}: import of '{name}' is not allowed in repairs")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in BANNED_CALLS:
            raise RepairRejected(f"{filename}: call to '{node.func.id}' is not allowed in repairs")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr != "__init__":
            raise RepairRejected(f"{filename}: dunder attribute access '{node.attr}' is not allowed")


def apply_edits(scenario: Scenario, edits: list[FileEdit]) -> dict[str, tuple[str, str]]:
    """Validate edits against the scenario and return {path: (before, after)}."""
    changed: dict[str, tuple[str, str]] = {}
    for edit in edits:
        if edit.path not in scenario.editable_files:
            raise RepairRejected(
                f"'{edit.path}' is not editable; allowed: {list(scenario.editable_files)}"
            )
        before = changed[edit.path][1] if edit.path in changed else scenario.read(edit.path)
        if edit.find == "":
            after = edit.replace
        else:
            count = before.count(edit.find)
            if count != 1:
                raise RepairRejected(
                    f"{edit.path}: search text must match exactly once, matched {count} times: "
                    f"{edit.find[:80]!r}"
                )
            after = before.replace(edit.find, edit.replace)
        if len(after.encode()) > MAX_FILE_BYTES:
            raise RepairRejected(f"{edit.path}: result exceeds {MAX_FILE_BYTES} bytes")
        original = changed[edit.path][0] if edit.path in changed else before
        changed[edit.path] = (original, after)

    for path, (_, after) in changed.items():
        if path.endswith(".json"):
            try:
                json.loads(after)
            except json.JSONDecodeError as exc:
                raise RepairRejected(f"{path}: invalid JSON after edit: {exc.msg}")
        if path in scenario.code_files:
            check_code_safety(after, path)
    return changed


def _sandbox_mode() -> str:
    return os.environ.get("TRACEGUARD_SANDBOX", "subprocess")


def is_docker_available() -> tuple[bool, str]:
    """Check if Docker daemon is responsive."""
    try:
        res = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            return True, "Docker engine active"
        first_err = (res.stderr.strip().splitlines() or ["Docker daemon not responding"])[0]
        return False, first_err
    except FileNotFoundError:
        return False, "Docker CLI not found on PATH"
    except Exception as exc:
        return False, str(exc)


def docker_mount_path(path: Path) -> str:
    """Format path for Docker -v volume mount across Windows and POSIX."""
    resolved = str(path.resolve()).replace("\\", "/")
    return f"{resolved}:/ws"


def build_docker_cmd(args: list[str], cwd: Path) -> list[str]:
    """Build hardened Docker run command for isolated replay."""
    image = os.environ.get("TRACEGUARD_SANDBOX_IMAGE", "python:3.12-slim")
    mount = docker_mount_path(cwd)
    return [
        "docker", "run", "--rm",
        "--network", "none",
        "--read-only",
        "--tmpfs", "/tmp:size=32m",
        "--memory", os.environ.get("TRACEGUARD_DOCKER_MEMORY", "256m"),
        "--cpus", os.environ.get("TRACEGUARD_DOCKER_CPUS", "1"),
        "--pids-limit", "64",
        "-v", mount,
        "-w", "/ws",
        image, "python", "-E", "-s", *args,
    ]


def _clean_env() -> dict[str, str]:
    keep = ("PATH", "SYSTEMROOT", "TEMP", "TMP", "WINDIR", "COMSPEC", "PATHEXT")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env.update({"PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"})
    return env


def _run(args: list[str], cwd: Path, timeout: float, mode: str) -> subprocess.CompletedProcess:
    if mode == "docker":
        cmd = build_docker_cmd(args, cwd)
    else:
        cmd = [sys.executable, "-E", "-s", *args]
    return subprocess.run(
        cmd, cwd=cwd, env=_clean_env(), capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace",
    )


def run_scenario(
    scenario: Scenario, edits: list[FileEdit] | None = None, timeout: float = 30.0
) -> SandboxRun:
    mode = _sandbox_mode()
    changed = apply_edits(scenario, edits or [])
    start = time.perf_counter()
    tmp = Path(tempfile.mkdtemp(prefix="traceguard-"))
    try:
        ws = tmp / "ws"
        shutil.copytree(scenario.path, ws, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(SCENARIO_ROOT / "_tracer.py", ws / "_tracer.py")
        for path, source in scenario.captured_files.items():
            (ws / path).write_text(source, encoding="utf-8")
        for path, (_, after) in changed.items():
            (ws / path).write_text(after, encoding="utf-8")

        try:
            agent = _run(["agent.py"], ws, timeout, mode)
        except subprocess.TimeoutExpired:
            return SandboxRun(ok=False, agent_exit_code=None, acceptance_passed=False, checks=[],
                              sandbox=mode, error=f"agent exceeded {timeout}s timeout",
                              duration_ms=(time.perf_counter() - start) * 1000)

        trace = None
        trace_file = ws / "trace.json"
        if trace_file.exists():
            trace = Trace.model_validate_json(trace_file.read_text(encoding="utf-8"))
            if scenario.captured_files:
                trace.metadata["captured_files"] = {
                    p: changed[p][1] if p in changed else s
                    for p, s in scenario.captured_files.items()
                }

        checks: list[AcceptanceCheck] = []
        error = None
        if agent.returncode != 0:
            last_line = (agent.stderr.strip().splitlines() or [""])[-1]
            error = f"agent crashed (exit {agent.returncode}): {last_line}"
            checks = [AcceptanceCheck(name="agent_runs", passed=False, detail=agent.stderr[-500:])]
        else:
            try:
                acc = _run(["acceptance.py"], ws, timeout, mode)
                checks = [AcceptanceCheck(**c) for c in json.loads(acc.stdout)]
                if acc.returncode != 0:
                    error = f"acceptance crashed (exit {acc.returncode}): {acc.stderr[-300:]}"
                elif not checks or len({c.name for c in checks}) != len(checks):
                    error = "acceptance must emit non-empty, uniquely named checks"
            except subprocess.TimeoutExpired:
                error = f"acceptance exceeded {timeout}s timeout"
            except (ValueError, TypeError) as exc:
                error = f"acceptance output unreadable: {exc}; stderr: {acc.stderr[-300:]}"

        if trace is None and error is None:
            error = "agent produced no execution trace"

        return SandboxRun(
            ok=error is None,
            agent_exit_code=agent.returncode,
            acceptance_passed=bool(checks) and all(c.passed for c in checks) and error is None,
            checks=checks,
            trace=trace,
            stdout=agent.stdout[-2000:],
            stderr=agent.stderr[-2000:],
            duration_ms=(time.perf_counter() - start) * 1000,
            sandbox=mode,
            error=error,
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
