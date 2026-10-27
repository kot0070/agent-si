-- K05 M3 STEP2 additive fingerprint index (INDEX ONLY, no table/column change).
CREATE INDEX IF NOT EXISTS idx_capability_evidence_fingerprint ON capability_evidence_records(environment_fingerprint);
