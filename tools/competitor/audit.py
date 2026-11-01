"""M-P4-143 competitor audit: findings that always carry source and quote.

Greenfield module adapted to the 0C architecture (RECORDS/day0/0C_ARCHITECTURE.md):
stdlib only, no network, no providers, deterministic. Audit input is plain
in-code data (a list of package records); every finding it returns carries
the record's source and quote fields, so a ranked review can always cite
where a claim was recorded and the verbatim line behind it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

RULE_RECORDED = "competitor-recorded"
RULE_SOURCE_MISSING = "competitor-source-missing"
RULE_QUOTE_MISSING = "competitor-quote-missing"

AUDIT_RULES = (
    RULE_SOURCE_MISSING,
    RULE_QUOTE_MISSING,
    RULE_RECORDED,
)


@dataclass(frozen=True)
class Finding:
    """One audited package record: rule plus package, source and quote."""

    rule: str
    package: str
    source: str
    quote: str
    detail: str


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def audit_packages(packages: Iterable[Mapping[str, Any]]) -> list[Finding]:
    """Audit package records into findings, each carrying source and quote.

    A record is a mapping with a non-empty ``package`` name plus ``source``
    and ``quote`` text. Records with both present are ``competitor-recorded``;
    a blank source yields ``competitor-source-missing`` (checked first); a
    blank quote yields ``competitor-quote-missing``. Foreign shapes (a mapping
    or string at the top level, a non-mapping entry, a missing/blank package
    name) raise TypeError/ValueError for the caller to report.
    """
    if isinstance(packages, (str, bytes)) or isinstance(packages, Mapping):
        raise TypeError("packages must be a list of package records")
    if not isinstance(packages, Iterable):
        raise TypeError("packages must be a list of package records")
    findings: list[Finding] = []
    for entry in packages:
        if not isinstance(entry, Mapping):
            raise TypeError("each package record must be a mapping")
        package = entry.get("package")
        if not isinstance(package, str) or package.strip() == "":
            raise ValueError("each package record needs a non-empty package name")
        source = _text(entry.get("source"))
        quote = _text(entry.get("quote"))
        if source.strip() == "":
            findings.append(
                Finding(
                    rule=RULE_SOURCE_MISSING,
                    package=package,
                    source=source,
                    quote=quote,
                    detail="package %s has no recorded source" % package,
                )
            )
        elif quote.strip() == "":
            findings.append(
                Finding(
                    rule=RULE_QUOTE_MISSING,
                    package=package,
                    source=source,
                    quote=quote,
                    detail="package %s has no recorded quote" % package,
                )
            )
        else:
            findings.append(
                Finding(
                    rule=RULE_RECORDED,
                    package=package,
                    source=source,
                    quote=quote,
                    detail="package %s recorded with source and quote" % package,
                )
            )
    return findings


def finding_to_dict(finding: Finding) -> dict[str, str]:
    """Plain JSON-ready record for one finding."""
    return {
        "rule": finding.rule,
        "package": finding.package,
        "source": finding.source,
        "quote": finding.quote,
        "detail": finding.detail,
    }


def findings_to_records(findings: Iterable[Finding]) -> list[dict[str, str]]:
    """Plain JSON-ready records for findings, in order."""
    return [finding_to_dict(finding) for finding in findings]
