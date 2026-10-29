from pathlib import Path
import pytest
from traceguard.sandbox import (
    docker_mount_path,
    build_docker_cmd,
    is_docker_available,
    run_scenario,
    _sandbox_mode,
)
from traceguard.scenarios import SCENARIOS


def test_docker_mount_path_normalizes_slashes():
    p = Path("C:\\some\\path\\to\\ws")
    mount = docker_mount_path(p)
    assert "\\\\" not in mount
    assert mount.endswith(":/ws")
    assert "/" in mount


def test_build_docker_cmd_structure():
    p = Path("C:/ws")
    cmd = build_docker_cmd(["agent.py"], p)
    assert cmd[0] == "docker"
    assert "run" in cmd
    assert "--network" in cmd
    assert "none" in cmd
    assert "--read-only" in cmd
    assert any(c.endswith(":/ws") for c in cmd)
    assert "python" in cmd
    assert "agent.py" in cmd


def test_is_docker_available_returns_tuple():
    avail, detail = is_docker_available()
    assert isinstance(avail, bool)
    assert isinstance(detail, str)


def test_docker_mode_selection_and_invocation(monkeypatch):
    import subprocess
    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        if "agent.py" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if "acceptance.py" in cmd:
            return subprocess.CompletedProcess(cmd, 0, '[{"name": "test_pass", "passed": true}]', "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("traceguard.sandbox._sandbox_mode", lambda: "docker")
    monkeypatch.setattr("subprocess.run", fake_run)
    run_scenario(SCENARIOS["tool_agent"])
    assert any(c[0] == "docker" for c in calls)
