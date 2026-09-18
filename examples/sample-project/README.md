# Synthetic config-loader sample

This is a fictional, self-contained project for demonstrating Oldhand. Every
hostname, record, configuration value, and failure mode is invented. Nothing
in this directory is derived from a customer, employer, or production system.

The loader deliberately selects either `defaults.json` or an environment file;
it never merges them. Run the repository-level demonstration from the Oldhand
checkout:

```bash
python3 -B examples/run_demo.py
```

The script copies this directory to a temporary workspace, shows the missing
staging value, then retrieves the reviewed Oldhand constraint that explains why
the loader must not be "simplified" into a merge.
