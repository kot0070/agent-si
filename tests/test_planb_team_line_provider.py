"""PLANB V2d: the chat team line never doubles the provider of a local model id."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent_si.runtime.devrun import engine  # noqa: E402


def _team(provider, model, mode="PINNED"):
    return [(role, {"provider": provider, "model": model, "mode": mode})
            for role in ("director", "manager", "worker", "auditor")]


def test_local_model_id_is_not_prefixed_twice():
    lines = engine._team_lines(_team("ollama", "ollama/muse-glimmer:30b"))
    assert lines == [
        "Team: director, manager, worker, auditor on "
        "ollama/muse-glimmer:30b (Pinned)"]


def test_cloud_model_without_prefix_keeps_provider_prefix():
    lines = engine._team_lines(_team("meta", "muse-spark-1.3-contributor"))
    assert "meta/muse-spark-1.3-contributor" in lines[0]


def test_per_role_lines_use_the_same_rule():
    team = _team("ollama", "ollama/muse-glimmer:30b")
    team[0] = ("director", {"provider": "meta", "model": "muse-spark-1.3",
                            "mode": "PINNED"})
    lines = engine._team_lines(team)
    assert lines[0].startswith("Role director: meta/muse-spark-1.3")
    assert lines[1].startswith("Role manager: ollama/muse-glimmer:30b ")
