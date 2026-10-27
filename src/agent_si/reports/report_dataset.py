"""K13 report dataset builder (Manifest §59 FINAL_REPORT; §47 REPORT_EXPORT).

Frames caller-supplied, record-derived sections into the frozen 37-key
report dataset. The builder adds no numbers of its own: every section value
must already come from authoritative stored records / MetricRecord rows, so
there is never AI-generated content in the output. Missing sections are
empty (never fabricated), and COST without a pricing snapshot is the
UNAVAILABLE marker (never zero or an estimate, per §11).

Core module: no database-driver or adapter imports (0C sec 12).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping

try:
    from iface.frozen_manifest import manifest  # noqa: F401  (frozen names source)
except ImportError:  # alternate layout: the iface/ directory itself on sys.path
    from frozen_manifest import manifest  # noqa: F401

REPORT_KEYS = (
    "PROJECT",
    "GOAL",
    "SCOPE",
    "ARCH",
    "PHASES",
    "TASKS",
    "RUNS",
    "MANAGERS",
    "AGENTS",
    "MODELS",
    "PROVIDERS",
    "ROUTES",
    "SPLIT_STRATEGIES",
    "ROUTING_DECISIONS",
    "FALLBACKS",
    "TIME",
    "TOKENS",
    "COST",
    "LOCAL_CALLS",
    "CLOUD_CALLS",
    "RETRIES",
    "REWORKS",
    "FAILURES",
    "INCIDENTS",
    "DEVIATIONS",
    "AMENDMENTS",
    "SECURITY",
    "TESTS",
    "AUDITS",
    "LIMITATIONS",
    "RISKS",
    "CONTEXT_INTEGRITY",
    "CONTEXT_VIOLATIONS",
    "BUDGET",
    "SDK_TRACING_POLICY",
    "USAGE_REPORTING_CAPABILITY",
    "FINAL_STATUS",
)
"""Frozen §59 key set, in manifest order."""

COST_UNAVAILABLE = "UNAVAILABLE"
"""COST marker when no pricing snapshot backs the calculation (§11)."""

_FORBIDDEN_KEY_PARTS = ("kit", "director", "records", "source", "secret", "private")
"""No output key may reference internals, provenance stores or raw secrets."""


class DatasetKeyError(ValueError):
    """Section map is not exactly the frozen key set."""


class DatasetSecretError(ValueError):
    """A section carries raw secret material; datasets carry refs, never values."""


class ReportDatasetBuilder:
    """Build the frozen report dataset from record-derived sections (§59)."""

    def __init__(self, known_secrets: Iterable[str] = ()) -> None:
        self._known_secrets = [s for s in known_secrets if s]

    def build(self, sections: Mapping[str, Any]) -> Dict[str, Any]:
        given = set(sections.keys())
        wanted = set(REPORT_KEYS)
        if given != wanted:
            raise DatasetKeyError(
                "dataset keys must be exactly the frozen set; "
                "missing=%s extra=%s"
                % (sorted(wanted - given), sorted(given - wanted))
            )
        for key in REPORT_KEYS:
            lowered = key.lower()
            for part in _FORBIDDEN_KEY_PARTS:
                if part in lowered:
                    raise DatasetKeyError(
                        "output key %r carries forbidden ref %r" % (key, part)
                    )
        dataset = {key: sections[key] for key in REPORT_KEYS}
        self._check_no_raw_secrets(dataset)
        if not sections.get("COST"):
            dataset["COST"] = COST_UNAVAILABLE
        return dataset

    def _check_no_raw_secrets(self, dataset: Mapping[str, Any]) -> None:
        if not self._known_secrets:
            return
        for key in REPORT_KEYS:
            blob = repr(dataset[key])
            for secret in self._known_secrets:
                if secret and secret in blob:
                    raise DatasetSecretError(
                        "section %r carries raw secret material" % key
                    )
