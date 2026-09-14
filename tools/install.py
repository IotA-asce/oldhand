#!/usr/bin/env python3
"""Put `lore` on PATH and point it at an archive.

Every command in the documentation reads `lore search ...`. Typing
`python /some/long/path/tools/lore/lore.py --root /another/long/path search ...`
instead is not a cosmetic difference: it is most of what decides whether a
tool gets reached for on a hunch, and reaching for it on a hunch is the entire
behaviour this system depends on.

What it changes, and nothing else:

  1. a `lore` launcher in a directory on your PATH
  2. a LORE_ROOT environment variable naming your archive

Both are reversible with `--uninstall`. Nothing is installed system-wide,
nothing needs administrator rights, and no file outside those two is touched
unless you pass --shell-rc.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

LORE_PY = Path(__file__).resolve().parent / "lore" / "lore.py"
IS_WINDOWS = platform.system() == "Windows"


def path_dirs() -> list[Path]:
    return [Path(p) for p in os.environ.get("PATH", "").split(os.pathsep) if p]


def pick_bin_dir() -> tuple[Path, bool]:
    """A directory for the launcher, and whether it is already on PATH."""
    preferred = [Path.home() / ".local" / "bin"]
    if IS_WINDOWS:
        preferred.append(Path.home() / "bin")
    else:
        preferred.append(Path.home() / "bin")
    on_path = {p.resolve() for p in path_dirs() if p.exists()}
    for d in preferred:
        try:
            if d.resolve() in on_path:
                return d, True
        except OSError:
            continue
    return preferred[0], False


def write_launcher(bin_dir: Path) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    if IS_WINDOWS:
        target = bin_dir / "lore.cmd"
        target.write_text(
            "@echo off\r\n"
            "REM Lore launcher. Written by tools/install.py.\r\n"
            "REM Delete this file, or run install.py --uninstall, to remove.\r\n"
            f'"{sys.executable}" "{LORE_PY}" %*\r\n',
            encoding="utf-8")
    else:
        target = bin_dir / "lore"
        target.write_text(
            "#!/bin/sh\n"
            "# Lore launcher. Written by tools/install.py.\n"
            "# Delete this file, or run install.py --uninstall, to remove.\n"
            f'exec "{sys.executable}" "{LORE_PY}" "$@"\n',
            encoding="utf-8")
        target.chmod(0o755)
        # A filesystem that drops the executable bit (a FAT or NTFS mount, a
        # restrictive umask) leaves a launcher that exists and cannot run,
        # which reads as "the install did nothing" rather than as an error.
        if not os.access(target, os.X_OK):
            print(f"WARNING: could not make {target} executable. Run:",
                  file=sys.stderr)
            print(f"  chmod +x {target}", file=sys.stderr)
    return target


def set_windows_env(name: str, value: str | None) -> None:
    """User-scope only. Never touches the machine environment."""
    if value is None:
        subprocess.run(["reg", "delete", "HKCU\\Environment", "/v", name, "/f"],
                       capture_output=True)
    else:
        subprocess.run(["setx", name, value], capture_output=True)


def shell_rc() -> Path | None:
    shell = os.environ.get("SHELL", "")
    home = Path.home()
    if "zsh" in shell:
        return home / ".zshrc"
    if "bash" in shell:
        for name in (".bashrc", ".bash_profile", ".profile"):
            if (home / name).exists():
                return home / name
        return home / ".bashrc"
    if "fish" in shell:
        return home / ".config" / "fish" / "config.fish"
    return None


MARKER = "# added by lore tools/install.py"


def main() -> int:
    args = sys.argv[1:]
    uninstall = "--uninstall" in args
    write_rc = "--shell-rc" in args
    positional = [a for a in args if not a.startswith("-")]

    bin_dir, on_path = pick_bin_dir()
    launcher = bin_dir / ("lore.cmd" if IS_WINDOWS else "lore")

    if uninstall:
        removed = []
        if launcher.exists():
            launcher.unlink()
            removed.append(str(launcher))
        if IS_WINDOWS:
            set_windows_env("LORE_ROOT", None)
            removed.append("LORE_ROOT (user environment)")
        else:
            rc = shell_rc()
            if rc and rc.exists() and MARKER in rc.read_text(encoding="utf-8"):
                kept = [l for l in rc.read_text(encoding="utf-8").splitlines()
                        if MARKER not in l and "LORE_ROOT" not in l]
                rc.write_text("\n".join(kept) + "\n", encoding="utf-8")
                removed.append(f"LORE_ROOT line in {rc}")
        print("removed:" if removed else "nothing to remove.")
        for r in removed:
            print(f"  {r}")
        if not IS_WINDOWS:
            print("\nOpen a new shell for the change to take effect.")
        return 0

    if not positional:
        print("usage: python tools/install.py <archive-directory> [--shell-rc]")
        print("       python tools/install.py --uninstall")
        print()
        print("The archive directory is the one holding your `memory/` folder.")
        print("Use `.` if you are standing in it.")
        return 2

    archive = Path(positional[0]).resolve()
    if not (archive / "memory").is_dir():
        print(f"No `memory/` directory inside {archive}.", file=sys.stderr)
        print("That is the archive root, not the Lore source tree. If you have not",
              file=sys.stderr)
        print("created an archive yet, `mkdir -p myarchive/memory` and pass that.",
              file=sys.stderr)
        return 1

    target = write_launcher(bin_dir)
    print(f"launcher   {target}")

    if IS_WINDOWS:
        set_windows_env("LORE_ROOT", str(archive))
        os.environ["LORE_ROOT"] = str(archive)
        print(f"LORE_ROOT  {archive}   (user environment)")
    else:
        line = f'export LORE_ROOT="{archive}"  {MARKER}'
        rc = shell_rc()
        if write_rc and rc:
            rc.parent.mkdir(parents=True, exist_ok=True)
            existing = rc.read_text(encoding="utf-8") if rc.exists() else ""
            if MARKER not in existing:
                with rc.open("a", encoding="utf-8") as fh:
                    fh.write("\n" + line + "\n")
            print(f"LORE_ROOT  appended to {rc}")
        else:
            print(f"LORE_ROOT  add this line to your shell profile"
                  f"{f' ({rc})' if rc else ''}:")
            print(f"             {line}")
            print("           or re-run with --shell-rc to have it appended.")

    print()
    if not on_path:
        print(f"WARNING: {bin_dir} is not on your PATH, so `lore` will not resolve.")
        print("Add it, or move the launcher somewhere that is. Everything else is done.")
        print()

    # Prove it works rather than asserting it does.
    env = dict(os.environ, LORE_ROOT=str(archive))
    probe = subprocess.run([sys.executable, str(LORE_PY), "--root", str(archive), "stats"],
                           capture_output=True, text=True, env=env)
    if probe.returncode == 0:
        first = [l for l in probe.stdout.splitlines() if l.strip()][:3]
        print("verified:")
        for l in first:
            print(f"  {l}")
    else:
        print("The archive did not open cleanly:", file=sys.stderr)
        print((probe.stderr or probe.stdout).strip()[:300], file=sys.stderr)
        return 1

    print()
    if IS_WINDOWS:
        print("Open a new terminal, then: lore search \"something you half remember\"")
    else:
        print("Open a new shell (or source your profile), then:")
        print("  lore search \"something you half remember\"")
    print()
    print("Undo any time with: python tools/install.py --uninstall")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
