# Expected terminal transcript

The recording must run from the repository root and display this command:

```console
$ python3 -B examples/run_demo.py
```

It must then show the following output exactly (apart from terminal wrapping):

```text
Oldhand synthetic demo — no network, account, model, or real project data

Before: no environment file selected
  DATABASE_URL = postgresql://demo-user@database.invalid/synthetic_app

After: synthetic staging file selected
  DATABASE_URL = <missing: staging must declare it explicitly>
  Interpretation: add DATABASE_URL to staging; do not merge defaults.

Oldhand search: why can't we simplify this config loader?
  Retrieved: synthetic_environment_config_replaces_defaults
  Summary: Do not merge `config/staging.json` with `config/defaults.json`. An environment file is a complete, reviewed replacement, so every required setting must be present in the environment file itself.

Oldhand show: synthetic_environment_config_replaces_defaults
  Title: Synthetic example: environment configuration replaces defaults
  Evidence: verified
```

The visual narrative is intentionally compact:

1. A coding agent sees that staging lacks a setting and might merge defaults.
2. Oldhand retrieves a reviewed constraint explaining why the apparent shortcut is unsafe.
3. The viewer sees that the record is local, verified, readable, and synthetic.

No credentials, customer names, production hostnames, or fabricated product
claims belong in the recording.
