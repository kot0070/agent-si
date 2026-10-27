"""K04 mini-drive integration skeleton (FAKE providers only).

Test-only harness skeleton for the K04 integration mini-drive. Lanes have
not landed, so everything here is stdlib + pytest: no src/ imports, no
network, no installs. Frozen V10 rules covered with fakes:

1. single-provider full-hierarchy pass on one model;
2. multi-provider run where the auditor leg differs from implementers;
3. per-provider spend caps enforced (hard caps block);
4. first provider error is a visible stop (recorded, run halts);
5. live E2E leg present but SKIPPED (Director-ordered gateway + user key
   on a non-Meta non-OpenAI provider; never network from tests);
6. run record carries agents, wall time, measured cost, rounds (from fakes).

Every loop is bounded (MAX_LEGS_PER_RUN / MAX_ROUNDS_PER_LEG).
"""

import time

import pytest

MAX_LEGS_PER_RUN = 8
MAX_ROUNDS_PER_LEG = 5


class ProviderError(Exception):
    """Simulated provider failure raised by a fake."""


class FakeProvider:
    """Deterministic fake provider: fixed cost per call, no network."""

    def __init__(self, provider_id, model_id, cost_per_call=0.01,
                 fail_on_call=None, spend_cap=None):
        self.provider_id = provider_id
        self.model_id = model_id
        self.cost_per_call = cost_per_call
        self.fail_on_call = fail_on_call
        self.spend_cap = spend_cap
        self.calls = 0
        self.spent = 0.0
        self.blocked_calls = 0

    def complete(self, prompt):
        """One fake completion; may raise ProviderError or report blocked."""
        self.calls += 1
        if self.fail_on_call is not None and self.calls >= self.fail_on_call:
            raise ProviderError(
                "%s/%s failed on call %d"
                % (self.provider_id, self.model_id, self.calls)
            )
        if (self.spend_cap is not None
                and self.spent + self.cost_per_call > self.spend_cap + 1e-12):
            self.blocked_calls += 1
            return {"blocked": True, "text": ""}
        self.spent += self.cost_per_call
        return {
            "blocked": False,
            "text": "fake:%s:%s#%d"
            % (self.provider_id, self.model_id, self.calls),
        }


class MiniDrive:
    """Skeleton mini-drive harness: ordered legs, halt on first stop."""

    def __init__(self, providers):
        self.providers = {}
        for provider in providers:
            self.providers[provider.provider_id] = provider

    def run(self, legs):
        """Execute legs in order; return the run record dict."""
        start = time.monotonic()
        record = {
            "agents": [],
            "wall_time_s": 0.0,
            "measured_cost": 0.0,
            "rounds": {},
            "status": "pass",
            "stops": [],
        }
        for leg in legs[:MAX_LEGS_PER_RUN]:
            agent = leg["agent"]
            provider = self.providers[leg["provider"]]
            rounds_done = 0
            stop = None
            for _ in range(min(int(leg.get("rounds", 1)), MAX_ROUNDS_PER_LEG)):
                try:
                    result = provider.complete(leg.get("prompt", "ping"))
                except ProviderError as exc:
                    stop = {
                        "kind": "provider_error",
                        "agent": agent,
                        "provider": provider.provider_id,
                        "model": provider.model_id,
                        "error": str(exc),
                    }
                    break
                if result["blocked"]:
                    stop = {
                        "kind": "spend_cap",
                        "agent": agent,
                        "provider": provider.provider_id,
                        "model": provider.model_id,
                        "spent": provider.spent,
                        "cap": provider.spend_cap,
                    }
                    break
                rounds_done += 1
            record["agents"].append(agent)
            record["rounds"][agent] = rounds_done
            if stop is not None:
                record["status"] = "halted"
                record["stops"].append(stop)
                break
        record["measured_cost"] = sum(
            provider.spent for provider in self.providers.values()
        )
        record["wall_time_s"] = time.monotonic() - start
        return record


def _single_provider_drive(**overrides):
    provider = FakeProvider("fake-uni", "fake-uni-model-1", **overrides)
    return provider, MiniDrive([provider])


def test_single_provider_full_hierarchy_pass():
    provider, drive = _single_provider_drive(cost_per_call=0.02)
    legs = [
        {"agent": "implementer-a", "provider": "fake-uni", "rounds": 2},
        {"agent": "implementer-b", "provider": "fake-uni", "rounds": 2},
        {"agent": "auditor", "provider": "fake-uni", "rounds": 2},
    ]
    record = drive.run(legs)
    assert record["status"] == "pass"
    assert record["stops"] == []
    assert record["agents"] == ["implementer-a", "implementer-b", "auditor"]
    assert record["rounds"] == {
        "implementer-a": 2, "implementer-b": 2, "auditor": 2,
    }
    assert provider.calls == 6
    assert record["measured_cost"] == pytest.approx(6 * 0.02)


def test_multi_provider_auditor_differs_from_implementers():
    impl = FakeProvider("fake-impl", "fake-impl-model-1", cost_per_call=0.01)
    audit = FakeProvider("fake-audit", "fake-audit-model-1", cost_per_call=0.05)
    drive = MiniDrive([impl, audit])
    legs = [
        {"agent": "implementer-a", "provider": "fake-impl", "rounds": 2},
        {"agent": "implementer-b", "provider": "fake-impl", "rounds": 1},
        {"agent": "auditor", "provider": "fake-audit", "rounds": 1},
    ]
    record = drive.run(legs)
    assert record["status"] == "pass"
    assert audit.provider_id != impl.provider_id
    assert audit.model_id != impl.model_id
    assert impl.calls == 3
    assert audit.calls == 1
    assert record["measured_cost"] == pytest.approx(3 * 0.01 + 1 * 0.05)


def test_per_provider_spend_caps_block():
    provider = FakeProvider(
        "fake-capped", "fake-capped-model-1",
        cost_per_call=0.02, spend_cap=0.04,
    )
    drive = MiniDrive([provider])
    record = drive.run([
        {"agent": "implementer-a", "provider": "fake-capped", "rounds": 3},
    ])
    assert record["status"] == "halted"
    assert record["rounds"] == {"implementer-a": 2}
    assert len(record["stops"]) == 1
    stop = record["stops"][0]
    assert stop["kind"] == "spend_cap"
    assert stop["provider"] == "fake-capped"
    assert provider.spent <= provider.spend_cap + 1e-12
    assert record["measured_cost"] == pytest.approx(provider.spent)


def test_first_provider_error_is_visible_stop_and_halts():
    bad = FakeProvider("fake-bad", "fake-bad-model-1", fail_on_call=1)
    good = FakeProvider("fake-good", "fake-good-model-1")
    drive = MiniDrive([bad, good])
    record = drive.run([
        {"agent": "implementer-a", "provider": "fake-bad", "rounds": 2},
        {"agent": "implementer-b", "provider": "fake-good", "rounds": 2},
    ])
    assert record["status"] == "halted"
    assert len(record["stops"]) == 1
    stop = record["stops"][0]
    assert stop["kind"] == "provider_error"
    assert stop["agent"] == "implementer-a"
    assert stop["error"]
    assert good.calls == 0
    assert "implementer-b" not in record["rounds"]


@pytest.mark.skip(
    reason="live E2E needs a Director-ordered gateway plus a user-supplied "
    "key on a non-Meta non-OpenAI provider; tests never touch the network"
)
def test_live_e2e_leg():
    # Intended live leg (never executed here): one auditor pass against a
    # non-Meta non-OpenAI provider through the Director-ordered gateway
    # with a user-supplied key. Body must never run without that order.
    raise AssertionError("live leg must stay skipped: no network from tests")


def test_run_record_carries_agents_walltime_cost_rounds():
    provider = FakeProvider("fake-rec", "fake-rec-model-1", cost_per_call=0.03)
    drive = MiniDrive([provider])
    record = drive.run([
        {"agent": "implementer-a", "provider": "fake-rec", "rounds": 2},
        {"agent": "auditor", "provider": "fake-rec", "rounds": 1},
    ])
    assert record["agents"] == ["implementer-a", "auditor"]
    assert isinstance(record["wall_time_s"], float)
    assert record["wall_time_s"] >= 0.0
    assert record["measured_cost"] == pytest.approx(provider.spent)
    assert record["measured_cost"] == pytest.approx(3 * 0.03)
    assert record["rounds"] == {"implementer-a": 2, "auditor": 1}
    assert sum(record["rounds"].values()) == provider.calls
