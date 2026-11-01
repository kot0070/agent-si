"""M-P4-143 competitor rank: rank rules plus ordered packages.

Rank rules map each audit rule to a severity (lower is more severe) so a
review reads gaps before recorded rows; ties break on package name, then
rule, so the order is deterministic for any input. Unknown rules sort last.
Stdlib only, no network, no providers, no I/O, deterministic.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Union

from tools.competitor.audit import (
    AUDIT_RULES,
    RULE_QUOTE_MISSING,
    RULE_RECORDED,
    RULE_SOURCE_MISSING,
    Finding,
)

RULE_SEVERITY = {
    RULE_SOURCE_MISSING: 0,
    RULE_QUOTE_MISSING: 1,
    RULE_RECORDED: 2,
}

UNKNOWN_SEVERITY = 99

Rankable = Union[Finding, Mapping[str, Any]]


def _parts(item: Rankable) -> tuple[str, str]:
    if isinstance(item, Finding):
        return item.rule, item.package
    if isinstance(item, Mapping):
        rule = item.get("rule")
        package = item.get("package")
        if not isinstance(rule, str) or not isinstance(package, str):
            raise TypeError("ranked entries need string rule and package")
        return rule, package
    raise TypeError("ranked entries must be findings or mappings")


def rank_key(item: Rankable) -> tuple[int, str, str]:
    """Sort key for one ranked entry: severity, package, rule."""
    rule, package = _parts(item)
    return (RULE_SEVERITY.get(rule, UNKNOWN_SEVERITY), package, rule)


def rank_findings(items: Iterable[Rankable]) -> list[Rankable]:
    """Return the entries ordered by the rank rules (stable, deterministic)."""
    return sorted(items, key=rank_key)


def ranked_packages(items: Iterable[Rankable]) -> list[str]:
    """Package names in ranked order."""
    return [_parts(item)[1] for item in rank_findings(items)]


__all__ = [
    "AUDIT_RULES",
    "RULE_QUOTE_MISSING",
    "RULE_RECORDED",
    "RULE_SEVERITY",
    "RULE_SOURCE_MISSING",
    "UNKNOWN_SEVERITY",
    "rank_findings",
    "rank_key",
    "ranked_packages",
]
