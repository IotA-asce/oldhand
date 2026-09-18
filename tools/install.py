#!/usr/bin/env python3
"""Put `oldhand` on PATH and point it at an archive.

Every command in the documentation reads `oldhand search ...`. Typing
`python /some/long/path/tools/oldhand/oldhand.py --root /another/long/path search ...`
instead is not a cosmetic difference: it is most of what decides whether a
tool gets reached for on a hunch, and reaching for it on a hunch is the entire
behaviour this system depends on.

What it changes, and nothing else:

  1. an `oldhand` launcher in a directory on your PATH
  2. a OLDHAND_ROOT environment variable naming your archive

Both are reversible with `--uninstall`. Nothing is installed system-wide,
nothing needs administrator rights, and no file outside those two is touched
unless you pass --shell-rc.
"""
from __future__ import annotations

import os
import platform
import re
import subprocess
import sys
from pathlib import Path

# The CLI now lives in an installable package. A clone-based launcher has
# to put src/ on PYTHONPATH because oldhand.cli uses package-relative
# imports and can no longer be run as a loose script.
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
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


def sh_quote(value) -> str:
    value = os.fspath(value)
    if IS_WINDOWS:
        return f'"{value}"'
    return "'" + value.replace("'", "'\\''") + "'"


def launcher_header() -> str:
    if IS_WINDOWS:
        return (
            "@echo off\r\n"
            "REM Oldhand launcher. Written by tools/install.py.\r\n"
            "REM Delete this file, or run install.py --uninstall, to remove.\r\n")
    return (
        "#!/bin/sh\n"
        "# Oldhand launcher. Written by tools/install.py.\n"
        "# Delete this file, or run install.py --uninstall, to remove.\n")


def owns_launcher(target: Path) -> bool:
    if target.is_symlink() or not target.is_file():
        return False
    try:
        with target.open(encoding="utf-8") as fh:
            return [fh.readline().rstrip("\r\n") for _ in range(3)] == launcher_header().splitlines()
    except (OSError, UnicodeError):
        return False


def write_launcher(bin_dir: Path) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    target = bin_dir / ("oldhand.cmd" if IS_WINDOWS else "oldhand")
    if (target.exists() or target.is_symlink()) and not owns_launcher(target):
        raise FileExistsError(f"Refusing to overwrite unowned launcher: {target}")
    if IS_WINDOWS:
        target.write_text(
            launcher_header()
            + f'set PYTHONPATH={sh_quote(SRC_DIR)}\r\n'
            + f'{sh_quote(sys.executable)} -m oldhand.cli %*\r\n',
            encoding="utf-8")
    else:
        target.write_text(
            launcher_header()
            + f'PYTHONPATH={sh_quote(SRC_DIR)} '
            + f'exec {sh_quote(sys.executable)} -m oldhand.cli "$@"\n',
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


def set_windows_env(name: str, value: str | None) -> bool:
    """Set a user-scope value, reporting failures rather than hiding them."""
    if value is None:
        command = ["reg", "delete", "HKCU\\Environment", "/v", name, "/f"]
        action = "remove"
    else:
        command = ["setx", name, value]
        action = "set"
    try:
        result = subprocess.run(command, capture_output=True, text=True)
    except OSError as exc:
        print(f"Could not {action} {name} in the Windows user environment: {exc}",
              file=sys.stderr)
        return False
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "no diagnostic returned").strip()
        print(f"Could not {action} {name} in the Windows user environment: {detail}",
              file=sys.stderr)
        return False
    return True


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


MARKER = "# added by oldhand tools/install.py"
PROFILE_ASSIGNMENT = re.compile(
    r"^(?:export OLDHAND_ROOT=(?:\"(?:[^\"\\]|\\[\s\S])*\"|'[^']*'(?:\\''[^']*')*)"
    r"|set -gx OLDHAND_ROOT '(?:[^'\\]|\\[\s\S])*')"
    r"[ \t]{2,}" + re.escape(MARKER) + r"(?:\r?\n|\Z)",
    re.MULTILINE)


def fish_quote(value: str) -> str:
    """Quote one literal for Fish's single-quoted string syntax."""
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def profile_assignment(archive: Path) -> str:
    """Return the owned profile line for the current shell."""
    value = str(archive)
    if "fish" in os.environ.get("SHELL", ""):
        return f"set -gx OLDHAND_ROOT {fish_quote(value)}  {MARKER}"
    return f"export OLDHAND_ROOT={sh_quote(value)}  {MARKER}"


def main() -> int:
    args = sys.argv[1:]
    uninstall = "--uninstall" in args
    write_rc = "--shell-rc" in args
    positional = [a for a in args if not a.startswith("-")]

    bin_dir, on_path = pick_bin_dir()
    launcher = bin_dir / ("oldhand.cmd" if IS_WINDOWS else "oldhand")

    if uninstall:
        removed = []
        failed = False
        if owns_launcher(launcher):
            launcher.unlink()
            removed.append(str(launcher))
        if IS_WINDOWS:
            if set_windows_env("OLDHAND_ROOT", None):
                removed.append("OLDHAND_ROOT (user environment)")
            else:
                failed = True
        else:
            rc = shell_rc()
            if rc and rc.exists() and MARKER in rc.read_text(encoding="utf-8"):
                with rc.open(encoding="utf-8", newline="") as fh:
                    text = fh.read()
                if PROFILE_ASSIGNMENT.search(text):
                    with rc.open("w", encoding="utf-8", newline="") as fh:
                        fh.write(PROFILE_ASSIGNMENT.sub("", text))
                    removed.append(f"OLDHAND_ROOT line in {rc}")
        print("removed:" if removed else "nothing to remove.")
        for r in removed:
            print(f"  {r}")
        if not IS_WINDOWS:
            print("\nOpen a new shell for the change to take effect.")
        return 1 if failed else 0

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
        print("That is the archive root, not the Oldhand source tree. If you have not",
              file=sys.stderr)
        print("created an archive yet, `mkdir -p myarchive/memory` and pass that.",
              file=sys.stderr)
        return 1

    try:
        target = write_launcher(bin_dir)
    except FileExistsError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"launcher   {target}")

    if IS_WINDOWS:
        if not set_windows_env("OLDHAND_ROOT", str(archive)):
            print(f"The launcher remains at {target}; remove it or retry after fixing "
                  "the Windows user environment.", file=sys.stderr)
            return 1
        os.environ["OLDHAND_ROOT"] = str(archive)
        print(f"OLDHAND_ROOT  {archive}   (user environment)")
    else:
        line = profile_assignment(archive)
        rc = shell_rc()
        if write_rc and rc:
            rc.parent.mkdir(parents=True, exist_ok=True)
            if rc.exists():
                with rc.open(encoding="utf-8", newline="") as fh:
                    existing = fh.read()
            else:
                existing = ""
            if PROFILE_ASSIGNMENT.search(existing):
                with rc.open("w", encoding="utf-8", newline="") as fh:
                    fh.write(PROFILE_ASSIGNMENT.sub(
                        lambda m: line + ("\r\n" if m.group(0).endswith("\r\n") else "\n"),
                        existing))
            else:
                with rc.open("a", encoding="utf-8", newline="") as fh:
                    fh.write("\n" + line + "\n")
            print(f"OLDHAND_ROOT  written to {rc}")
        else:
            print(f"OLDHAND_ROOT  add this line to your shell profile"
                  f"{f' ({rc})' if rc else ''}:")
            print(f"             {line}")
            print("           or re-run with --shell-rc to have it appended.")

    print()
    if not on_path:
        print(f"WARNING: {bin_dir} is not on your PATH, so `oldhand` will not resolve.")
        print("Add it, or move the launcher somewhere that is. Everything else is done.")
        print()

    # Prove it works rather than asserting it does.
    env = dict(os.environ, OLDHAND_ROOT=str(archive),
               PYTHONPATH=os.pathsep.join(
                   [str(SRC_DIR)] + ([os.environ["PYTHONPATH"]]
                                     if os.environ.get("PYTHONPATH") else [])))
    probe = subprocess.run([sys.executable, "-m", "oldhand.cli",
                            "--root", str(archive), "stats"],
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
        print("Open a new terminal, then: oldhand search \"something you half remember\"")
    else:
        print("Open a new shell (or source your profile), then:")
        print("  oldhand search \"something you half remember\"")
    print()
    print("Undo any time with: python tools/install.py --uninstall")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
