import argparse
import ast
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
ADDED_FILES = (
    "tools/verify.py", "tools/test_e2e.py", "tools/test_install.py",
    "tools/lore/test_lore.py", "tools/migrate/test_migrations.py",
)


def run_checks(root):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    for path in sorted((root / "tools").rglob("*.py")):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 10))
    for directory in ("tools/lore", "tools/migrate", "tools"):
        subprocess.run(
            [sys.executable, "-B", "-m", "unittest", "discover", "-s", directory,
             "-p", "test_*.py", "-v"], cwd=root, env=env, check=True)
    subprocess.run([sys.executable, "-B", "tools/lore/lore.py", "selftest"],
                   cwd=root, env=env, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean-checkout", action="store_true")
    args = parser.parse_args()
    if not args.clean_checkout:
        run_checks(ROOT)
        return 0
    patch = subprocess.run(["git", "diff", "HEAD", "--binary"], cwd=ROOT,
                           capture_output=True, check=True).stdout
    with tempfile.TemporaryDirectory(prefix="lore-verify-") as temporary:
        checkout = Path(temporary) / "checkout"
        subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", str(ROOT), str(checkout)],
                       check=True)
        if patch:
            subprocess.run(["git", "apply", "--whitespace=error"], cwd=checkout,
                           input=patch, check=True)
        for name in ADDED_FILES:
            source = ROOT / name
            target = checkout / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
        subprocess.run(["git", "diff", "--check"], cwd=checkout, check=True)
        run_checks(checkout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
