---
schema_version: 1
id: synthetic_payment_idempotency
type: constraint
status: current
importance: critical
scope: subsystem
risk: critical
durability: invariant
evidence: verified
topics: [payments, webhooks, retries]
created_at: 2026-09-18T00:00:00+00:00
updated_at: 2026-09-18T00:00:00+00:00
expires_at: null
relations: {}
---

# Synthetic: payment webhooks require idempotency keys

## Summary

Handle every payment webhook as an at-least-once delivery and deduplicate it
using the provider event identifier before any ledger mutation.

## Knowledge

The fictional payment gateway retries after timeouts, including after a
successful charge. Retrying is safe only when the persisted event identifier
has already guarded the ledger write.

## Verification

Verified by the synthetic duplicate-delivery scenario.
