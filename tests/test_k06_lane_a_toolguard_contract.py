"""STEP 1 behaviour contract for the Lane A toolguard prefix.

Covers frozen interfaces G1 (guard evaluate), G3 (permission ladder),
G2 (action-execution record usage), the ASK card shape, and G5
(SecretRef opacity). Every error code has its own condition, every
route reaches the real implementation through its entry point, and
every call surface is wired. Bodies are `...`, so the behaviour
assertions below are RED until STEP 2 implements them after HD
freeze.
"""

import importlib.util
import pathlib

import pytest

TOOLGUARD_DIR = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src"
    / "agent_si"
    / "toolguard"
)

STUB_FILES = (
    "__init__.py",
    "guard.py",
    "permissions.py",
    "actions.py",
    "ask.py",
    "secrets.py",
)


def _load(name, filename):
    path = TOOLGUARD_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_package_files_exist():
    for filename in STUB_FILES:
        assert (TOOLGUARD_DIR / filename).is_file()


def test_modules_import():
    for filename in STUB_FILES:
        _load("tg_import_" + filename.replace(".py", ""), filename)


def test_call_surfaces_wired():
    guard = _load("tg_wired_guard", "guard.py")
    permissions = _load("tg_wired_permissions", "permissions.py")
    actions = _load("tg_wired_actions", "actions.py")
    ask = _load("tg_wired_ask", "ask.py")
    secrets = _load("tg_wired_secrets", "secrets.py")
    assert callable(guard.evaluate)
    assert guard.ACTION_CLASSES == ("R0", "R1", "R2", "R3")
    assert callable(permissions.check_permission)
    assert callable(actions.build_action_record)
    assert callable(actions.verify_provider_or_prior_state)
    assert callable(actions.record_attempt)
    assert callable(ask.build_ask_card)
    assert callable(ask.resume_from_token)
    assert callable(secrets.make_secret_ref)
    assert callable(secrets.is_secret_ref)


def test_no_shell_strings():
    for filename in STUB_FILES:
        text = (TOOLGUARD_DIR / filename).read_text(encoding="utf-8")
        for token in ("shell=True", "os.system", "subprocess", "Popen"):
            assert token not in text


def test_stubs_hold_no_logic():
    for filename in (
        "guard.py",
        "permissions.py",
        "actions.py",
        "ask.py",
        "secrets.py",
    ):
        text = (TOOLGUARD_DIR / filename).read_text(encoding="utf-8")
        assert "NotImplementedError" not in text
        assert "TODO" not in text


def test_g1_evaluate_returns_decision_shape():
    guard = _load("tg_eval_shape", "guard.py")
    result = guard.evaluate(
        argv=["echo", "hi"],
        action_class="R0",
        auth={"task": "t1"},
    )
    assert result["decision"] in ("allow", "ask", "deny")
    assert isinstance(result["reason"], str)
    assert isinstance(result["evidence_ref"], str)


def test_g3_r0_requires_task_authorization():
    permissions = _load("tg_perm_r0", "permissions.py")
    result = permissions.check_permission(
        action_class="R0",
        auth={},
        generated=False,
    )
    assert result["error"] == permissions.ERR_R0_NOT_TASK_AUTHORIZED


def test_g3_r1_requires_contract():
    permissions = _load("tg_perm_r1", "permissions.py")
    result = permissions.check_permission(
        action_class="R1",
        auth={},
        generated=False,
    )
    assert result["error"] == permissions.ERR_R1_CONTRACT_REQUIRED


def test_g3_r2_requires_director_record():
    permissions = _load("tg_perm_r2", "permissions.py")
    result = permissions.check_permission(
        action_class="R2",
        auth={"contract": "c1"},
        generated=False,
    )
    assert result["error"] == permissions.ERR_R2_DIRECTOR_RECORD_REQUIRED


def test_g3_r3_requires_user_record():
    permissions = _load("tg_perm_r3", "permissions.py")
    result = permissions.check_permission(
        action_class="R3",
        auth={"contract": "c1"},
        generated=False,
    )
    assert result["error"] == permissions.ERR_R3_USER_RECORD_REQUIRED


def test_g3_generated_never_gains_privilege():
    permissions = _load("tg_perm_gen", "permissions.py")
    result = permissions.check_permission(
        action_class="R1",
        auth={"contract": "c1"},
        generated=True,
    )
    assert result["error"] == permissions.ERR_GENERATED_PRIVILEGE_DENIED


def test_g2_build_action_record_carries_fields():
    actions = _load("tg_actions_build", "actions.py")
    record = actions.build_action_record(
        action_id="a1",
        idempotency_key="k1",
        authorization_ref="auth1",
        attempt=1,
        status="pending",
    )
    assert record["action_id"] == "a1"
    assert record["idempotency_key"] == "k1"
    assert record["authorization_ref"] == "auth1"
    assert record["attempt"] == 1
    assert record["status"] == "pending"


def test_g2_provider_key_else_prior_state_verify():
    actions = _load("tg_actions_verify", "actions.py")
    record = {
        "action_id": "a1",
        "idempotency_key": "k1",
        "authorization_ref": "auth1",
        "attempt": 1,
        "status": "pending",
    }
    result = actions.verify_provider_or_prior_state(
        record=record,
        provider_key="pk1",
        prior_state=None,
    )
    assert result["ok"] is True


def test_g2_record_attempt_keeps_attempt_and_status():
    actions = _load("tg_actions_attempt", "actions.py")
    record = {
        "action_id": "a1",
        "idempotency_key": "k1",
        "authorization_ref": "auth1",
        "attempt": 1,
        "status": "pending",
    }
    result = actions.record_attempt(record=record, status="done")
    assert result["attempt"] == 2
    assert result["status"] == "done"


def test_ask_card_shape():
    ask = _load("tg_ask_build", "ask.py")
    card = ask.build_ask_card(
        ask_id="q1",
        kind="approve",
        summary="Allow this action?",
        options=["yes", "no"],
        resume_token="rt1",
    )
    assert card["ask_id"] == "q1"
    assert card["kind"] == "approve"
    assert card["summary"] == "Allow this action?"
    assert card["options"] == ["yes", "no"]
    assert card["resume_token"] == "rt1"


def test_ask_resume_token_roundtrip():
    ask = _load("tg_ask_resume", "ask.py")
    resumed = ask.resume_from_token(resume_token="rt1")
    assert resumed["resume_token"] == "rt1"


def test_g5_secret_ref_opaque_string():
    secrets = _load("tg_secrets_opaque", "secrets.py")
    ref = secrets.make_secret_ref(ref="vault://k")
    assert isinstance(ref, str)
    assert secrets.is_secret_ref(ref) is True


# HD SECURITY binding: every write entry gets a no-token AND a wrong-token
# refusal test; refusal shape is PermissionError (uniform across lane A).
# NOTE: build_action_record is a pure constructor with no credential
# surface of its own, so its token tests go through the verify/attempt
# flow: a record missing authorization_ref is the no-token equivalent and
# a record carrying a forged authorization_ref is the wrong-token
# equivalent; both must refuse with PermissionError.
def test_g2_verify_no_token_refuses():
    actions = _load("tg_actions_verify_notoken", "actions.py")
    record = {
        "action_id": "a1",
        "idempotency_key": "k1",
        "attempt": 1,
        "status": "pending",
    }
    with pytest.raises(PermissionError):
        actions.verify_provider_or_prior_state(
            record=record,
            provider_key=None,
            prior_state=None,
        )


def test_g2_verify_wrong_token_refuses():
    actions = _load("tg_actions_verify_badtoken", "actions.py")
    record = {
        "action_id": "a1",
        "idempotency_key": "k1",
        "authorization_ref": "forged-bad-token",
        "attempt": 1,
        "status": "pending",
    }
    with pytest.raises(PermissionError):
        actions.verify_provider_or_prior_state(
            record=record,
            provider_key=None,
            prior_state=None,
        )


def test_g2_record_attempt_no_token_refuses():
    actions = _load("tg_actions_attempt_notoken", "actions.py")
    record = {
        "action_id": "a1",
        "idempotency_key": "k1",
        "attempt": 1,
        "status": "pending",
    }
    with pytest.raises(PermissionError):
        actions.record_attempt(record=record, status="done")


def test_g2_record_attempt_wrong_token_refuses():
    actions = _load("tg_actions_attempt_badtoken", "actions.py")
    record = {
        "action_id": "a1",
        "idempotency_key": "k1",
        "authorization_ref": "forged-bad-token",
        "attempt": 1,
        "status": "pending",
    }
    with pytest.raises(PermissionError):
        actions.record_attempt(record=record, status="done")
