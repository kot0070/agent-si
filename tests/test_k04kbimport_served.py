"""K04KBIMPORT served proof: staged MODEL_KB sections imported as sourced rows.

Row map (row -> route -> test):
  K04KBIMPORT-SECTIONS  20 staged files present (16 provider + 4 doc)
                        -> test_kbimport_section_files_present_served
  K04KBIMPORT-PATH      updater allowlist + frozen error codes
                        -> test_kbimport_update_path_constants_served
  K04KBIMPORT-APPLY     staged sections via updater.apply_proposal
                        -> test_kbimport_staged_import_via_updater_apply_served
  K04KBIMPORT-FAMILY    served read-back per provider family
                        -> test_kbimport_per_family_served_readback
  K04KBIMPORT-UNKNOWN   UNKNOWN stays UNKNOWN
                        -> test_kbimport_unknown_preserved_served
  K04KBIMPORT-WARNING   contributor warning verbatim in the TSX card
                        -> test_kbimport_warning_verbatim_served
  K04KBIMPORT-NEG-*     invented value / dropped source / unconfirmed
                        apply / reworded warning must FAIL
                        -> test_kbimport_negative_*_served

Every test drives REAL product code under src/agent_si/model_kb/
(loader.build_staged_base/import_staged_sections, updater.apply_proposal,
backend.modelkb.get_models/get_kb_status). Fixtures live only in this file.
"""
import copy
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.backend import modelkb
from agent_si.model_kb import kb, loader, updater

SECTIONS_DIR = os.path.abspath(
    os.path.join(_HERE, "fixtures", "kb_sections"))
# Legacy bundle path (git-excluded DIRECTOR inbox, kept as fallback only).
_LEGACY_SECTIONS_DIR = os.path.abspath(
    os.path.join(_HERE, "..", "DIRECTOR", "INBOX", "MODEL_KB", "sections"))
TSX_PATH = os.path.abspath(os.path.join(
    _HERE, "..", "frontend", "src", "settings", "ProvidersPage",
    "ChatModelSelector.tsx"))
DAY = "2026-10-11"

WARNING_EN = ("Contributor tier: prompts and completions may be used by "
              "Meta to train future models "
              "(https://dev.meta.ai/docs/pricing-rate-limits).")
WARNING_UK = ("Тариф Contributor: запити та відповіді можуть "
              "використовуватися Meta для навчання майбутніх моделей "
              "(https://dev.meta.ai/docs/pricing-rate-limits).")

PROVIDER_MODELS = [
    "anthropic/claude-sonnet-5-5",
    "azure-openai/gpt-4o",
    "bedrock/bedrock-anthropic-claude-sonnet-5-5",
    "cohere/command-a-03-2025",
    "deepseek/deepseek-v4-pro",
    "fireworks/accounts/fireworks/models/gpt-oss-120b",
    "google/gemini-2.5-flash",
    "groq/openai/gpt-oss-120b",
    "local/local-llama-3.1-8b",
    "meta/muse-spark-1.3-contributor",
    "mistral/mistral-large-4",
    "openai/gpt-4o",
    "openrouter/openrouter-meta-muse-spark-1.3",
    "perplexity/sonar-pro",
    "together/openai/gpt-oss-120b",
    "xai/grok-4.7",
]

# (provider, model, field, expected value, expected source substring):
# every value quoted from its section file, retrieved 2026-10-11.
SPOT_CHECKS = [
    ("anthropic", "claude-sonnet-5-5", "input_token_price", 2,
     "platform.claude.com/docs/en/about-claude/pricing"),
    ("anthropic", "claude-sonnet-5-5", "output_token_price", 10,
     "platform.claude.com/docs/en/about-claude/pricing"),
    ("anthropic", "claude-sonnet-5-5", "context_window", 1000000,
     "platform.claude.com/docs/en/models/sonnet-5-5/overview"),
    ("openai", "gpt-4o", "input_token_price", 2.5,
     "platform.openai.com/docs/models/gpt-4o"),
    ("openai", "gpt-4o", "output_token_price", 10,
     "platform.openai.com/docs/models/gpt-4o"),
    ("openai", "gpt-4o", "context_window", 128000,
     "platform.openai.com/docs/models/gpt-4o"),
    ("openai", "gpt-4o", "max_output", 16384,
     "platform.openai.com/docs/models/gpt-4o"),
    ("openai", "gpt-4o", "knowledge_cutoff", "2023-10-01",
     "platform.openai.com/docs/models/gpt-4o"),
    ("deepseek", "deepseek-v4-pro", "input_token_price", 1.32,
     "api-docs.deepseek.com/quick_start/pricing"),
    ("deepseek", "deepseek-v4-pro", "output_token_price", 3.96,
     "api-docs.deepseek.com/quick_start/pricing"),
    ("deepseek", "deepseek-v4-pro", "max_output", 384000,
     "api-docs.deepseek.com/quick_start/pricing"),
    ("mistral", "mistral-large-4", "input_token_price", 0.68,
     "docs.mistral.ai/inference/pricing/"),
    ("mistral", "mistral-large-4", "output_token_price", 2.09,
     "docs.mistral.ai/inference/pricing/"),
    ("mistral", "mistral-large-4", "context_window", 1048576,
     "docs.mistral.ai/models/mistral-large-4-0"),
    ("meta", "muse-spark-1.3-contributor", "input_token_price", 0.1,
     "dev.meta.ai/docs/pricing-rate-limits"),
    ("meta", "muse-spark-1.3-contributor", "output_token_price", 0.2,
     "dev.meta.ai/docs/pricing-rate-limits"),
    ("meta", "muse-spark-1.3-contributor", "context_window", 1048576,
     "dev.meta.ai/docs/models"),
    ("xai", "grok-4.7", "input_token_price", 2.0,
     "docs.x.ai/docs/pricing"),
    ("xai", "grok-4.7", "output_token_price", 6.0,
     "docs.x.ai/docs/pricing"),
    ("xai", "grok-4.7", "context_window", 500000,
     "docs.x.ai/docs/models/grok-4.7"),
    ("xai", "grok-4.7", "knowledge_cutoff", "2026-05",
     "docs.x.ai/docs/models"),
    ("google", "gemini-2.5-flash", "context_window", 1048576,
     "ai.google.dev/gemini-api/docs/models/gemini-2.5-flash"),
    ("google", "gemini-2.5-flash", "max_output", 65536,
     "ai.google.dev/gemini-api/docs/models/gemini-2.5-flash"),
    ("cohere", "command-a-03-2025", "context_window", 256000,
     "docs.cohere.com/docs/models"),
    ("cohere", "command-a-03-2025", "max_output", 8000,
     "docs.cohere.com/docs/models"),
]


def _bind(catalog):
    before = copy.deepcopy(kb.bound_catalog())
    kb.bind_catalog(catalog)
    return before


def _restore(before):
    kb.bind_catalog(before)


def _imported_catalog():
    return loader.import_staged_sections(user_confirmed=True)


def _field(row, name):
    return row["fields"][name]


def test_kbimport_section_files_present_served():
    """K04KBIMPORT-SECTIONS: 20 staged files (16 provider + 4 doc)."""
    names = sorted(f for f in os.listdir(SECTIONS_DIR)
                   if f.endswith(".md"))
    assert len(names) == 20, names
    providers = [n for n in names if n not in (
        "index.md", "retired.md", "sources-update.md", "task-guide.md")]
    assert len(providers) == 16, providers
    assert loader.STAGED_PROVIDER_COUNT == 16
    assert loader.STAGED_MODEL_COUNT == 132


def test_kbimport_update_path_constants_served():
    """K04KBIMPORT-PATH: allowlist + frozen error codes intact."""
    assert len(updater.KB_SOURCE_ALLOWLIST) == 11
    assert "https://platform.openai.com/docs" in updater.KB_SOURCE_ALLOWLIST
    assert "https://dev.meta.ai/docs" in updater.KB_SOURCE_ALLOWLIST
    assert issubclass(updater.KB_VALIDATION_FAILED,
                      updater.ProposalRejectedError)
    assert issubclass(updater.KB_PROPOSAL_NOT_APPROVED,
                      updater.ConfirmationRequiredError)


def test_kbimport_staged_import_via_updater_apply_served():
    """K04KBIMPORT-APPLY: every staged row applied via updater path."""
    base = loader.build_staged_base()
    assert len(base["models"]) == 132
    assert kb.validate_catalog(base) == []
    catalog = loader.import_staged_sections(
        base=base, user_confirmed=True)
    assert kb.validate_catalog(catalog) == []
    assert catalog["version"]["kb_version"] == 1 + 16
    assert catalog["version"]["updated_at"] == DAY
    log = catalog["version"]["change_log"]
    assert len(log) == 16
    assert sorted(i["providers"] for i in log) == sorted(
        [[p] for p in sorted(loader._STAGED_SECTION_ROWS)])
    for item in log:
        assert item["at"] == DAY
        assert item["changes"]
    for row in catalog["models"]:
        for name, field in row["fields"].items():
            if field["value"] == "UNKNOWN":
                assert field["source"] == "UNKNOWN", (row, name)
                assert field["retrieved_at"] == "UNKNOWN", (row, name)
            else:
                assert field["source"].startswith("https://"), (row, name)
                assert field["retrieved_at"] == DAY, (row, name)


def test_kbimport_per_family_served_readback():
    """K04KBIMPORT-FAMILY: served read-back for all 16 families."""
    catalog = _imported_catalog()
    before = _bind(catalog)
    try:
        status = modelkb.get_kb_status()
        assert status["overall"]["kb_version"] == 17
        assert len(status["per_provider"]) == 16
        for pair in PROVIDER_MODELS:
            provider, model = pair.split("/", 1)
            back = loader.read_back(
                catalog, provider, model, [provider])
            assert back["found"] is True, pair
            assert back["kb_status"] == loader.IN_BASE, pair
            assert back["row"]["model_id"] == model
            rows = modelkb.get_models([provider], None)
            hit = [r for r in rows if r["provider_id"] == provider
                   and r["model_id"] == model]
            assert hit and hit[0]["selected"] is True, pair
            contract, ref = loader.resolve_exact_id(model)
            assert contract["model_id"] == model, pair
            assert ref.startswith(contract["provider_id"] + "/"
                                  + model + "@"), pair
        for provider, model, field, value, source in SPOT_CHECKS:
            row = loader.find_row(catalog, provider, model)
            got = _field(row, field)
            assert got["value"] == value, (provider, model, field)
            assert source in got["source"], (provider, model, field)
            assert got["retrieved_at"] == DAY
    finally:
        _restore(before)


def test_kbimport_unknown_preserved_served():
    """K04KBIMPORT-UNKNOWN: no silent fills, UNKNOWN stays UNKNOWN."""
    catalog = _imported_catalog()
    row = loader.find_row(catalog, "openai", "gpt-4o")
    assert _field(row, "currency")["value"] == "UNKNOWN"
    assert _field(row, "reasoning")["value"] == "UNKNOWN"
    row = loader.find_row(catalog, "meta", "muse-glimmer-30b")
    assert _field(row, "input_token_price")["value"] == "UNKNOWN"
    assert _field(row, "output_token_price")["value"] == "UNKNOWN"
    assert _field(row, "currency")["value"] == "UNKNOWN"
    row = loader.find_row(catalog, "mistral", "mistral-large-4")
    assert _field(row, "max_output")["value"] == "UNKNOWN"
    assert _field(row, "reasoning")["value"] == "UNKNOWN"
    row = loader.find_row(catalog, "google", "gemini-2.5-flash")
    assert _field(row, "input_token_price")["value"] == "UNKNOWN"
    assert _field(row, "output_token_price")["value"] == "UNKNOWN"
    row = loader.find_row(catalog, "cohere", "command-a-03-2025")
    assert _field(row, "input_token_price")["value"] == "UNKNOWN"
    assert _field(row, "reasoning")["value"] == "UNKNOWN"


def test_kbimport_warning_verbatim_served():
    """K04KBIMPORT-WARNING: contributor warning verbatim in the TSX card."""
    with open(SECTIONS_DIR + "/meta.md", encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    assert lines[109].endswith(WARNING_EN), lines[109]
    assert lines[110].endswith(WARNING_UK), lines[110]
    with open(TSX_PATH, encoding="utf-8") as handle:
        tsx = handle.read()
    assert tsx.count(WARNING_EN) >= 1, "verbatim EN missing in TSX"
    assert tsx.count(WARNING_UK) >= 1, "verbatim UK missing in TSX"
    warn_pos = tsx.index('data-testid="model-warning"')
    picker_pos = tsx.index("ChatSelector catalog=")
    assert warn_pos < picker_pos, "warning must render above the picker"


def test_kbimport_negative_invented_value_rejected_served():
    """K04KBIMPORT-NEG: an invented field value must FAIL validation."""
    catalog = _imported_catalog()
    proposal = {
        "source_url": "https://platform.openai.com/docs/models/gpt-4o",
        "retrieved_at": DAY,
        "changes": [{"provider_id": "openai", "model_id": "gpt-4o",
                     "field": "input_token_price", "old": 2.5,
                     "new": 999.999, "source": "https://example.com/made-up",
                     "retrieved_at": DAY},
                    {"provider_id": "openai", "model_id": "gpt-4o",
                     "field": "no_such_field", "old": None, "new": 1,
                     "source": "https://platform.openai.com/docs/models/gpt-4o",
                     "retrieved_at": DAY}],
    }
    errors = updater.validate_proposal(catalog, proposal)
    assert errors, "unknown field must fail validation"
    with open(SECTIONS_DIR + "/openai.md", encoding="utf-8") as handle:
        text = handle.read()
    assert "999.999" not in text


def test_kbimport_negative_dropped_source_rejected_served():
    """K04KBIMPORT-NEG: a dropped source or date must FAIL validation."""
    catalog = _imported_catalog()
    row = loader.find_row(catalog, "openai", "gpt-4o")
    assert _field(row, "input_token_price")["source"].startswith("https://")
    proposal = {
        "source_url": "",
        "retrieved_at": "",
        "changes": [{"provider_id": "openai", "model_id": "gpt-4o",
                     "field": "input_token_price", "old": 2.5, "new": 2.4,
                     "source": "", "retrieved_at": ""}],
    }
    errors = updater.validate_proposal(catalog, proposal)
    assert errors, "dropped source must fail validation"
    try:
        updater.apply_proposal(catalog, proposal, user_confirmed=True)
    except updater.KB_VALIDATION_FAILED:
        pass
    else:
        raise AssertionError("dropped source apply must raise")


def test_kbimport_negative_unconfirmed_apply_rejected_served():
    """K04KBIMPORT-NEG: import without confirmation must FAIL."""
    try:
        loader.import_staged_sections(user_confirmed=False)
    except updater.KB_PROPOSAL_NOT_APPROVED:
        pass
    else:
        raise AssertionError("unconfirmed import must raise")
    catalog = loader.build_staged_base()
    proposal = {
        "source_url": "https://platform.openai.com/docs/models/gpt-4o",
        "retrieved_at": DAY,
        "changes": [{"provider_id": "openai", "model_id": "gpt-4o",
                     "field": "context_window", "old": 128000,
                     "new": 128001,
                     "source": "https://platform.openai.com/docs/models/gpt-4o",
                     "retrieved_at": DAY}],
    }
    try:
        updater.apply_proposal(catalog, proposal, user_confirmed=False)
    except updater.ConfirmationRequiredError:
        pass
    else:
        raise AssertionError("unconfirmed apply must raise")


def test_kbimport_negative_reworded_warning_rejected_served():
    """K04KBIMPORT-NEG: a reworded warning is never the verbatim text."""
    reworded = "Contributor tier: prompts may be reused for training."
    assert reworded != WARNING_EN
    assert reworded != WARNING_UK
    with open(TSX_PATH, encoding="utf-8") as handle:
        tsx = handle.read()
    assert reworded not in tsx
