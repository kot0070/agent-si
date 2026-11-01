# K04NEXT2 K1 lane (CODER-1 Harrier) — recorded loopback replay, pools side.
"""Replay a committed recorded loopback E2E through the real pool path.

Row M-P1-25 is one recorded live E2E on a non-Meta non-OpenAI provider for
MVP: the artifact is the recorded HTTP round-trip, and the replay test
itself uses no network. These helpers validate the artifact (row id,
provider, recorded HTTP 200) and serve it as a real pool binding plus real
KB facts, so the replay routes through ``agent_si.routing.pools``
verbatim. Standard library plus in-repo routing ports only: no machine
paths, no secrets, no vendor or model defaults.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from agent_si.routing import kb_port as KB
from agent_si.routing import pools as P

#: Row id this replay serves.
RECORDED_ROW = "M-P1-25"

#: Recorded HTTP status that counts as a live E2E round-trip.
RECORDED_HTTP_OK = 200

#: Providers excluded by the row definition (Meta, OpenAI).
FORBIDDEN_PROVIDERS = ("meta", "openai")

#: Artifact keys the replay reads; all must be present and non-empty.
REQUIRED_KEYS = ("row", "provider_id", "model", "messages", "http",
                 "reply_received", "response_record", "recorded_at",
                 "base_url")


def load_recorded_artifact(path):
    """Load one recorded loopback artifact from JSON."""
    with open(path, "r", encoding="utf-8") as handle:
        artifact = json.load(handle)
    if not isinstance(artifact, Mapping):
        raise ValueError(
            "M-P1-25 recorded artifact must be a JSON object: %r" % (path,))
    return dict(artifact)


def check_recorded_e2e(artifact) -> dict:
    """Validate a recorded M-P1-25 loopback E2E artifact.

    Returns an ``{"ok": True, ...}`` evidence dict naming row, provider
    and model. Refuses with ValueError naming M-P1-25 when the row id,
    provider, recorded HTTP status, or any required key is wrong: a
    tampered or foreign artifact never replays as this row.
    """
    if not isinstance(artifact, Mapping):
        raise ValueError("M-P1-25 recorded artifact must be a mapping")
    missing = [key for key in REQUIRED_KEYS if not artifact.get(key)]
    if missing:
        raise ValueError(
            "M-P1-25 recorded artifact misses keys: %s" % sorted(missing))
    if artifact.get("row") != RECORDED_ROW:
        raise ValueError(
            "M-P1-25 replay needs row %r, got %r"
            % (RECORDED_ROW, artifact.get("row")))
    provider = artifact.get("provider_id")
    if provider in FORBIDDEN_PROVIDERS:
        raise ValueError(
            "M-P1-25 replay needs a non-Meta non-OpenAI provider, got %r"
            % (provider,))
    http = artifact.get("http") or {}
    if http.get("status") != RECORDED_HTTP_OK:
        raise ValueError(
            "M-P1-25 replay needs recorded HTTP %d, got %r"
            % (RECORDED_HTTP_OK, http.get("status")))
    return {"ok": True, "row": RECORDED_ROW,
            "provider_id": provider, "model": artifact.get("model")}


def recorded_pool_binding(artifact, role: str = "worker",
                          project_id: str = "p1",
                          strategy: str = "FALLBACK_ORDER",
                          provider_type: str = "local"):
    """Serve the recorded (provider, model) pair as a real pool binding."""
    checked = check_recorded_e2e(artifact)
    return P.make_binding(
        role, project_id,
        [P.PoolMember(checked["provider_id"], checked["model"],
                      "primary", provider_type)],
        strategy=strategy)


def recorded_kb_facts(artifact, task_fit: float = 0.9,
                      quality: float = 0.9) -> KB.KbModelFacts:
    """Serve real KB facts for the recorded (provider, model) pair."""
    checked = check_recorded_e2e(artifact)
    recorded_at = artifact.get("recorded_at")
    return KB.KbModelFacts(
        provider=checked["provider_id"], model=checked["model"],
        task_fit={"coding": task_fit, "text": task_fit,
                  "general": task_fit},
        strict_pass_rate=quality, tolerant_pass_rate=quality,
        sample_count=50, confidence=0.9, freshness="CURRENT",
        input_price=0.01, output_price=0.03,
        modalities=("text", "tools", "coding"), assessed_risk="LOW",
        fields_state="MEASURED", verified_static=False,
        source="k04next2-k1", measured_at=recorded_at,
        latency_ms=400.0)
