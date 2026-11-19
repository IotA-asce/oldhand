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
        guide = run("guide", "lifecycle")
        if "status guide-example historical" not in guide or archive.exists():
            raise RuntimeError("Installed guide is missing or accessed the archive")
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
        run("new", "--id", "guide-example", "--title", "Fixture cache invalidation",
            "--type", "lesson", "--importance", "normal", "--topics", "fixture-cache",
            "--summary", "Fixture cache entries must be invalidated when their source changes.")
        if "guide-example" not in run("search", "fixture cache"):
            raise RuntimeError("Installed guide walkthrough could not find its record")
        run("status", "guide-example", "historical")
        shown = json.loads(run("show", "guide-example", "--json"))
        if shown["status"] != "historical":
            raise RuntimeError("Installed guide walkthrough did not retire its record")
        if "guide-example" not in run("search", "--history", "fixture cache"):
            raise RuntimeError("Installed guide walkthrough lost retired history")
        log = archive / ".oldhand" / "retrieval.jsonl"
        log.write_text(json.dumps({"at": "2026-11-15", "action": "search",
                                   "query": "private fixture query", "returned": []})
                       + "\nmalformed fixture row\n\n", encoding="utf-8")
        exported = base / "metrics-export.json"
        run("metrics", "--export", str(exported))
        metrics = json.loads(exported.read_text(encoding="utf-8"))
        if (metrics["metrics_schema"] != 2
                or "zero_result_searches" not in metrics["latest"]["retrieval"]):
            raise RuntimeError("Installed wheel did not export schema-2 rate counters")
        retrieval = metrics["latest"]["retrieval"]
        if (not retrieval["log_available"]
                or (retrieval["valid_events"], retrieval["malformed_events"],
                    retrieval["blank_lines"]) != (1, 1, 1)
                or retrieval["first_event_date"] != "2026-11-15"
                or retrieval["last_event_date"] != "2026-11-15"):
            raise RuntimeError("Installed wheel exported incorrect log provenance")
        if "private fixture query" in exported.read_text(encoding="utf-8"):
            raise RuntimeError("Installed metrics export leaked query content")
        print("Installed wheel passed offline guide, create/find/retire, native console, "
              "Unicode, Obsidian, and metrics provenance checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
