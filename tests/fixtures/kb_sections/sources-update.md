# Sources & update procedure (updated 2026-10-11)

## The two classes

FACT class: one value per field, written exactly as the official provider page states it, cited with that field `sources.<field>` URL and retrieval date. If no official page states the value, the text says UNKNOWN and points to the checked page in `sources_checked`.
ANALYSIS class: strengths, weaknesses, best_for, avoid_for, role_notes, task_fit, tier and similar judgments, written in own words, each tagged `(analysis)`, followed by one line `Analysis basis: <analysis_sources URLs>`.

## How to update

To refresh one provider: re-fetch its official model, pricing and deprecation pages; compare ids, context/output numbers and prices against the catalog record; edit the changed record; set UNKNOWN where the page no longer states a value; bump dates; re-run the validator.
Azure special case: the Azure pricing hub exposes no static per-model token rates, so per-model prices stay UNKNOWN with the explanation kept in `sources_checked_note`, never in `sources`.
Never cite generic pages, other-model pages, or third-party registries as FACT sources; one URL may cover several fields and is then cited once per sentence group.

## Sources & retrieval dates

- Class rules: OUT/UPDATE_GUIDE.md — 2026-10-11.
- Source policy: OUT/SOURCES.md — 2026-10-11.
