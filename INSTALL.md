# Install

Two things make the difference between a tool you reach for on a hunch and one
you reach for when you are already sure: a short command, and not having to
say where your archive is.

```bash
python tools/install.py /path/to/your/archive
```

That is the whole install. It writes a `lore` launcher into a directory on
your PATH and sets `LORE_ROOT` to your archive, then opens the archive to
prove it worked. Nothing is installed system-wide, nothing needs
administrator rights, and nothing else on your machine is touched.

The argument is the directory containing your `memory/` folder, not the Lore
source tree. If you have not made one yet:

```bash
mkdir -p ~/knowledge/memory
python tools/install.py ~/knowledge
```

Open a new terminal afterwards, because environment changes do not reach
shells that were already running.

```bash
lore search "something you half remember"
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

The installer is a convenience, not a dependency. Nothing in Lore requires it.

### macOS and Linux

```sh
cat > ~/.local/bin/lore <<'EOF'
#!/bin/sh
exec python3 "$HOME/path/to/lore/tools/lore/lore.py" "$@"
EOF
chmod +x ~/.local/bin/lore
echo 'export LORE_ROOT="$HOME/path/to/your/archive"' >> ~/.zshrc   # or ~/.bashrc
```

Pass `--shell-rc` to the installer to have that last line appended for you. It
is not done by default, because silently editing someone's shell profile is a
larger liberty than writing one file they asked for.

### Windows

```bat
@echo off
"C:\Path\To\python.exe" "C:\Path\To\lore\tools\lore\lore.py" %*
```

Save as `lore.cmd` in any directory on your PATH (`%USERPROFILE%\.local\bin`
is a common one), then:

```bat
setx LORE_ROOT "C:\Path\To\Your\Archive"
```

`setx` writes to the user environment, not the machine one, and takes effect
in new terminals only.

### Without either

Every command works with explicit paths, which is what CI should use anyway:

```bash
python tools/lore/lore.py --root /path/to/archive search "..."
```

`--root` beats `LORE_ROOT`, which beats auto-detection by walking up from the
current directory looking for a `memory/` folder.

## Checking it

```bash
lore validate     # every record parses and the schema holds
lore stats        # names the archive it resolved, so scope is never ambiguous
lore selftest     # ranking invariants, no archive needed
```

`lore stats` printing the wrong root is the failure worth looking for: it
means auto-detection found a different `memory/` folder before yours, usually
because you are standing inside one. Set `LORE_ROOT`, or pass `--root`.

## Requirements

Python 3.10 or newer, and PyYAML:

```bash
python -m pip install -r tools/lore/requirements.txt
```

SQLite comes with Python. There is nothing else: no server, no service, no
account, no network access at any point.
