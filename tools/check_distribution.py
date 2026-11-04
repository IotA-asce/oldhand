"""Install and exercise the built wheel on the current native platform."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import venv


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    wheels = list((ROOT / "dist").glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit("Expected exactly one built wheel in dist/")
    for artifact in sorted((ROOT / "dist").iterdir()):
        if artifact.is_file():
            print(hashlib.sha256(artifact.read_bytes()).hexdigest(), artifact.name)
    # Exercise real Windows Unicode/space paths through pip's console entry
    # point, without relying on a checkout import or a developer-mode symlink.
    with tempfile.TemporaryDirectory(prefix="oldhand-package-") as temporary:
        base = Path(temporary) / "环境 with spaces"
        environment = base / "venv"
        venv.create(environment, with_pip=True)
        binaries = environment / ("Scripts" if os.name == "nt" else "bin")
        python = binaries / ("python.exe" if os.name == "nt" else "python")
        cli = binaries / ("oldhand.exe" if os.name == "nt" else "oldhand")
        env = {key: value for key, value in os.environ.items()
               if key not in {"PYTHONPATH", "OLDHAND_ROOT", "LORE_ROOT"}}
        subprocess.run([str(python), "-m", "pip", "install", str(wheels[0])],
                       env=env, check=True)
        archive = base / "记忆 archive"

        def run(*args: str) -> str:
            result = subprocess.run([str(cli), "--root", str(archive), *args],
                                    cwd=base, env=env, capture_output=True,
                                    encoding="utf-8", check=True)
            return result.stdout

        print(run("--version").strip())
        run("init", str(archive))
        run("obsidian")
        note = json.loads(run("new", "--id", "unicode-note", "--title", "认证 memory",
                              "--type", "lesson", "--importance", "normal",
                              "--topics", "跨平台", "--json"))
        shown = json.loads(run("show", "unicode-note", "--json"))
        if shown["title"] != "认证 memory":
            raise RuntimeError("Installed CLI lost Unicode record content")
        results = json.loads(run("search", "认证", "--json"))
        if results["results"][0]["id"] != "unicode-note":
            raise RuntimeError("Installed CLI could not retrieve Unicode record")
        text = (archive / note["path"]).read_text(encoding="utf-8")
        if "## Obsidian graph" not in text:
            raise RuntimeError("Installed CLI did not generate native graph links")
        if not json.loads(run("validate", "--json"))["valid"]:
            raise RuntimeError("Installed CLI generated an invalid archive")
        print("Installed wheel passed native console, Unicode paths/content, search, and Obsidian checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
