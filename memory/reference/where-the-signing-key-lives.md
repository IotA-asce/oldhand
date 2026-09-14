---
schema_version: 1
id: lore_example_signing_key_location
type: reference
status: current
importance: normal
scope: repository
risk: medium
durability: long_lived
evidence: verified
topics:
  - deployment
  - config
created_at: 2026-03-02T10:00:00+00:00
updated_at: 2026-03-02T10:00:00+00:00
expires_at: null
relations: {}
---

# Where the release signing key lives, and who can read it

## Summary

The signing key is in the build system's secret store under `release/signing`,
not in the cloud key vault where every other credential lives. Rotating it
needs a pipeline variable update in the same change, or the next release fails
at the signing step with a misleading "file not found".

## Knowledge

The split exists for a dull historical reason: signing predates the key vault
and moving it was never worth a release freeze. Nothing marks the key as
special in the vault, so looking there and finding nothing is the expected
outcome, not evidence that it has been deleted.

The failure mode after a rotation is the confusing part. The signing step
reads the key path from a pipeline variable, so a rotated key with a stale
variable reports a missing file rather than an auth error, which sends people
hunting for a deleted secret that is sitting there under a new name.

**How to apply.** Rotate the key and update the pipeline variable in one
change, then run a release to a throwaway target before the next real one.

## Verification

Checked against the secret store's access list and one rotation.

## References

- the release pipeline definition, signing step
