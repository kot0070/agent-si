# KB keeper guide: new-model price path (K09-B)

When a new model goes live, the keeper refreshes the price path so savings
numbers stay honest. The shapes come from
`RECORDS/day1/K04_INTERFACE_STUB_v2_MAP13.py` (frozen `PricingSnapshot` and
`CostLine`, sections 3.5/2) and are exercised by
`RECORDS/day1/K04_CONTRACT_TEST.py` (sha256 `e4f8ad33…`).

## Shapes

`PricingSnapshot` identifies one priced model:

```text
pricing_snapshot_id, provider_id, model_id, currency,
effective_at, source, input_token_price, output_token_price,
cached_token_price, reasoning_token_price, request_price
```

`CostLine` carries the computed cost for one usage record:

```text
amount, currency, pricing_snapshot_id
```

`amount` may be `None`, which means UNAVAILABLE — never zero-fill it.

## Flow

1. The keeper registers the new model as a fresh `PricingSnapshot`
   (new `pricing_snapshot_id`, `effective_at` of the switch-over).
2. Usage is costed against that snapshot into a `CostLine`; its
   `pricing_snapshot_id` must equal the snapshot's.
3. The line's `amount` flows into the record cost:
   `record_hit(role, agent, tokens, line.amount)` (likewise for miss /
   web-fallback records), so `savings_report()["cost"]` equals the sum of
   stored record costs.

## Behaviour contract, test fakes only

Real pricing calls are out of scope for this repo: behaviour is pinned only
by the test-local stand-ins `FakePricingSnapshot` / `FakeCostLine` in
`tests/test_k09b_contract.py` (marker
`FAKE-OF: RECORDS/day1/K04_INTERFACE_STUB_v2.py`), which mirror the frozen
field lists above. The keeper price test stores `line.amount` through
`record_hit` and asserts it reappears in `list_records()` costs and in the
`savings_report()` total.
