"""Deployment assets are checked for syntax and internal consistency (no Docker daemon needed)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]


def test_shell_scripts_parse_and_are_executable():
    for script in sorted((REPO / "deploy" / "scripts").glob("*.sh")):
        subprocess.run(["bash", "-n", str(script)], check=True)
        assert script.stat().st_mode & 0o111, f"{script.name} is not executable"


def test_compose_files_are_valid_yaml_with_expected_services():
    files = {"homeassistant.yml": {"homeassistant"}, "brain.yml": {"ollama", "companion-api", "companion-worker"}, "vault.yml": {"companion-vault"}}
    for name, services in files.items():
        data = yaml.safe_load((REPO / "deploy" / "compose" / name).read_text())
        assert set(data["services"]) == services, name
    ha = yaml.safe_load((REPO / "deploy" / "compose" / "homeassistant.yml").read_text())["services"]["homeassistant"]
    assert ha["network_mode"] == "host" and ha["privileged"] is True and any(v.endswith(":/config") for v in ha["volumes"])
    brain = yaml.safe_load((REPO / "deploy" / "compose" / "brain.yml").read_text())["services"]
    assert brain["ollama"]["environment"]["OLLAMA_NUM_PARALLEL"] == "1" and brain["ollama"]["ports"][0].startswith("127.0.0.1:")


def test_systemd_units_have_placeholders_and_hardening():
    units = list((REPO / "deploy" / "systemd").glob("*.service"))
    assert {u.name for u in units} >= {"companion-api.service", "companion-worker.service", "companion-vault.service", "companion-backup.service", "companion-audio.service"}
    for u in units:
        text = u.read_text()
        assert "__REPO__" in text and "ExecStart=" in text, u.name
        if u.name != "companion-audio.service":
            assert "__USER__" in text and "ProtectSystem=strict" in text, u.name
    worker = (REPO / "deploy" / "systemd" / "companion-worker.service").read_text()
    assert re.search(r"^Nice=10", worker, re.M) and "IOSchedulingClass" in worker  # background work yields to the interactive path
    timer = (REPO / "deploy" / "systemd" / "companion-backup.timer").read_text()
    assert "OnCalendar=*-*-* 02:00:00" in timer and "Persistent=true" in timer


def test_check_host_runs_here():
    out = subprocess.run(["bash", str(REPO / "deploy" / "scripts" / "check-host.sh")], capture_output=True, text=True, check=False)
    assert "architecture supported" in out.stdout and "Result:" in out.stdout


def test_dockerfile_installs_only_locked_dependencies():
    df = (REPO / "deploy" / "docker" / "Dockerfile").read_text()
    assert "uv sync --all-packages --frozen --no-dev" in df and "USER companion" in df and "HEALTHCHECK" in df
