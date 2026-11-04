# Install

Oldhand runs on Windows, macOS, and Linux with Python 3.10 or newer. Install the
published package in your preferred Python environment:

```bash
python -m pip install --upgrade oldhand==0.6.0b3
oldhand init ~/knowledge
```

On Windows, follow the PowerShell instructions below. For an isolated console
installation, `pipx install oldhand==0.6.0b3` also works. Version `0.6.0b3` is
the first release with required Windows CI and native wheel-install checks.

## Optional source-checkout launcher

Two things make the difference between a tool you reach for on a hunch and one
you reach for when you are already sure: a short command, and not having to
say where your archive is.

```bash
python tools/install.py /path/to/your/archive --shell-rc
```

That is the whole install. It writes a `oldhand` launcher into a directory on
your PATH, writes `OLDHAND_ROOT` to the profile for a recognized Zsh, Bash, or
Fish shell, then opens the archive to prove it worked. Nothing is installed
system-wide, nothing needs administrator rights, and nothing else on your
machine is touched.

Without `--shell-rc`, the installer deliberately leaves your profile alone
and prints the exact line to add yourself; a new terminal will not inherit
`OLDHAND_ROOT` until that line is saved to its profile.

The argument is the directory containing your `memory/` folder, not the Oldhand
source tree. If you have not made one yet:

```bash
mkdir -p ~/knowledge/memory
python tools/install.py ~/knowledge --shell-rc
```

Open a new terminal afterwards, because environment changes do not reach
shells that were already running.

```bash
oldhand search "something you half remember"
```

## Undoing it

```bash
python tools/install.py --uninstall
```

Removes the launcher and the variable. It leaves your archive completely
alone: every record is a Markdown file you can read, move or delete with
ordinary tools, which is the point of storing them that way.

---

## Doing it by hand

The installer is a convenience, not a dependency. Nothing in Oldhand requires it.

### macOS and Linux

```sh
cat > ~/.local/bin/oldhand <<'EOF'
#!/bin/sh
PYTHONPATH="$HOME/path/to/oldhand/src" exec python3 -m oldhand.cli "$@"
EOF
chmod +x ~/.local/bin/oldhand
echo 'export OLDHAND_ROOT="$HOME/path/to/your/archive"' >> ~/.zshrc   # or ~/.bashrc
```

Pass `--shell-rc` to the installer to have that last line appended for you. It
is not done by default, because silently editing someone's shell profile is a
larger liberty than writing one file they asked for.

For Fish, use Fish syntax instead:

```fish
set -gx OLDHAND_ROOT "$HOME/path/to/your/archive"
```

When `SHELL` identifies Fish, `--shell-rc` writes the matching `set -gx`
line to `~/.config/fish/config.fish`.

### Windows

Native Windows is tested on Python 3.10–3.13, including the installed console
entry point, Unicode paths and records, JSON output, and Obsidian navigation.
WSL is not required. Install Python 3.10 or newer, then use PowerShell:

```powershell
py -3 -m pip install --user --upgrade oldhand==0.6.0b3
py -3 -m oldhand.cli init "$env:USERPROFILE\knowledge"
$env:OLDHAND_ROOT = "$env:USERPROFILE\knowledge"
[Environment]::SetEnvironmentVariable("OLDHAND_ROOT", $env:OLDHAND_ROOT, "User")
py -3 -m oldhand.cli selftest
py -3 -m oldhand.cli stats
py -3 -m oldhand.cli obsidian
```

The `py -3 -m oldhand.cli` form works without adding Python's Scripts directory
to PATH. If that directory is already on PATH, use `oldhand` directly. A pipx
installation provides the same short command after `pipx ensurepath` and a
new terminal.

For a source checkout, install its dependencies and run:

```powershell
py -3 -m pip install -r requirements.txt
py -3 tools/install.py "$env:USERPROFILE\knowledge"
```

This writes an owned `oldhand.cmd` launcher and sets `OLDHAND_ROOT` for your
user account. If it reports that the launcher directory is missing from PATH,
add that directory through Windows user environment settings, then open a new
terminal. Reinstallation and removal preserve unrelated launchers. Symlinks
are never overwritten; creating symlinks for your own files may require
Windows Developer Mode or permission, but Oldhand does not require symlinks
for ordinary use.

### Without either

Every command works with explicit paths, which is what CI should use anyway:

```bash
python -m pip install -e .
python -m oldhand.cli --root /path/to/archive search "..."
```

`--root` beats `OLDHAND_ROOT`, which beats auto-detection by walking up from the
current directory looking for a `memory/` folder.

## Checking it

```bash
oldhand validate     # every record parses and the schema holds
oldhand stats        # names the archive it resolved, so scope is never ambiguous
oldhand selftest     # ranking invariants, no archive needed
```

`oldhand stats` printing the wrong root is the failure worth looking for: it
means auto-detection found a different `memory/` folder before yours, usually
because you are standing inside one. Set `OLDHAND_ROOT`, or pass `--root`.

## Requirements

Python 3.10 or newer, and PyYAML:

```bash
python -m pip install -r requirements.txt
```

SQLite comes with Python. There is nothing else: no server, no service, no
account, no network access at any point.
