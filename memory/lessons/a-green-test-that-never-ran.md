---
schema_version: 1
id: lore_example_green_test_never_ran
type: lesson
status: current
importance: high
scope: subsystem
risk: high
durability: long_lived
evidence: verified
topics:
  - testing
  - messaging
created_at: 2026-01-14T10:00:00+00:00
updated_at: 2026-01-14T10:00:00+00:00
expires_at: null
relations: {}
---

# Fictional example: a rejected message still commits its offset

## Summary

In this fictional example, a consumer test asserted the service stayed healthy and the offset advanced,
and passed while the handler never ran: the message was rejected by a header
check before deserialization, and a rejected message is still committed. Assert
a side effect that can only exist if the handler body executed.

## Knowledge

Every rejection path in front of a handler still commits the offset, so offset
progress proves the poll loop is alive and nothing more. Two silent gates sat
ahead of this handler: a missing tenant header, then licence validation.

The test was measuring the gate, not the enum conversion it was written for.
It was caught only by grepping the run log for the poison value and finding
zero hits.

**How to apply.** An assertion that the system stayed healthy is not evidence
the system did the work. Prove the code under test was entered with something
that can only be true if it ran: a log line naming your input, a spy on the
handler, a row it would have written. If the only evidence is "nothing broke",
the test is equally consistent with the input having been discarded on arrival.

The same shape appears without a message queue: any loop whose body might not
execute needs its iteration count printed. `for f in $(some_command)` over an
empty result looks exactly like every file matching.

## Verification

Reproduced by adding the missing header, which changed the log and the
conclusion.

## References

- fictional inbound-message filter
