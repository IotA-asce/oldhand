"""Oldhand: git-tracked institutional memory for coding agents.

Records are ordinary Markdown on disk and remain canonical. The SQLite
index under the archive's dot-directory is derived state and can be deleted
and rebuilt at any time.
"""

__version__ = "0.6.0b1"

__all__ = ["__version__"]
