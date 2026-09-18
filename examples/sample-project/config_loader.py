"""Fictional config loader used only by the Lore demonstration.

An environment file is a complete replacement for defaults.  That apparently
odd contract is intentional: deployments provide a fully reviewed, rendered
configuration instead of an implicit merge of two files.
"""

from __future__ import annotations

import json
from pathlib import Path


def load_config(config_dir: Path, environment: str | None = None) -> dict[str, object]:
    """Return defaults, or the complete selected environment configuration."""
    filename = "defaults.json" if environment is None else f"{environment}.json"
    with (config_dir / filename).open(encoding="utf-8") as handle:
        return json.load(handle)
