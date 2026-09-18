# Install

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
exec python3 "$HOME/path/to/oldhand/src/oldhand/cli.py" "$@"
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

### Windows (not supported yet)

Windows is **not a supported platform** for this release. CI runs the full
suite on Windows as an informational `windows-preview` job, and it currently
fails: `show --json` returns no output under the end-to-end harness, and the
installer's symlink handling is unverified. The instructions below are what
we expect to work once those defects are fixed; treat them as unsupported.

```bat
@echo off
"C:\Path\To\python.exe" "C:\Path\To\oldhand\tools\oldhand\oldhand.py" %*
```

Save as `oldhand.cmd` in any directory on your PATH (`%USERPROFILE%\.local\bin`
is a common one), then:

```bat
setx OLDHAND_ROOT "C:\Path\To\Your\Archive"
```

`setx` writes to the user environment, not the machine one, and takes effect
in new terminals only.

### Without either

Every command works with explicit paths, which is what CI should use anyway:

```bash
python src/oldhand/cli.py --root /path/to/archive search "..."
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
