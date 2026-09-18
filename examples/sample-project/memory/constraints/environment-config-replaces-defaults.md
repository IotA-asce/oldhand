---
schema_version: 1
id: synthetic_environment_config_replaces_defaults
type: constraint
status: current
importance: critical
scope: repository
risk: critical
durability: invariant
evidence: verified
topics:
  - config
  - deployment
created_at: 2026-09-18T00:00:00+00:00
updated_at: 2026-09-18T00:00:00+00:00
expires_at: null
relations: {}
---

# Synthetic example: environment configuration replaces defaults

## Summary

Do not merge `config/staging.json` with `config/defaults.json`. An environment
file is a complete, reviewed replacement, so every required setting must be
present in the environment file itself.

## Knowledge

The fictional deployment renderer consumes exactly one configuration document.
When an environment file exists, it replaces the defaults document. A merge
would make unreviewed defaults reach a deployment and would hide omissions in
the environment configuration.

The missing `DATABASE_URL` in the deliberately incomplete synthetic staging
file is the signal to fix the staging file, not a reason to change the loader.

## Verification

`examples/run_demo.py` renders the defaults and synthetic staging values. The
staging result intentionally lacks `DATABASE_URL` and the Oldhand search below
retrieves this record.

## References

- `config_loader.py`
- `config/defaults.json`
- `config/staging.json`
