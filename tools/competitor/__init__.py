"""M-P4-143 competitor package: audit records into ranked findings.

Public surface: ``audit.audit_packages`` returns findings that carry
``source`` and ``quote``; ``rank.rank_findings`` orders them by the rank
rules; ``cli.main`` serves both over the ``audit``/``rank`` commands;
``__main__`` is the CLI entry. Stdlib only, no network, no providers,
deterministic.
"""

from tools.competitor.audit import (
    AUDIT_RULES,
    RULE_QUOTE_MISSING,
    RULE_RECORDED,
    RULE_SOURCE_MISSING,
    Finding,
    audit_packages,
    finding_to_dict,
    findings_to_records,
)
from tools.competitor.rank import (
    RULE_SEVERITY,
    UNKNOWN_SEVERITY,
    rank_findings,
    rank_key,
    ranked_packages,
)

__all__ = [
    "AUDIT_RULES",
    "RULE_QUOTE_MISSING",
    "RULE_RECORDED",
    "RULE_SEVERITY",
    "RULE_SOURCE_MISSING",
    "UNKNOWN_SEVERITY",
    "Finding",
    "audit_packages",
    "finding_to_dict",
    "findings_to_records",
    "rank_findings",
    "rank_key",
    "ranked_packages",
]
