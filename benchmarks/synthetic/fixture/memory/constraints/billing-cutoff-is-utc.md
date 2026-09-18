---
schema_version: 1
id: synthetic_billing_uses_utc
type: constraint
status: current
importance: high
scope: subsystem
risk: high
durability: invariant
evidence: verified
topics: [billing, time, utc]
created_at: 2026-09-18T00:00:00+00:00
updated_at: 2026-09-18T00:00:00+00:00
expires_at: null
relations: {}
---

# Synthetic: billing daily boundaries are UTC

## Summary

Every billing daily cutoff uses UTC, not a customer, browser, or server local
timezone.

## Knowledge

The fictional billing ledger groups events by a UTC day. Local timezone
conversion is a presentation concern and must not move an event across the
ledger boundary.

## Verification

Verified by the synthetic midnight-boundary examples.
