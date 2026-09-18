import argparse
import ast
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
# Test files live outside the package, and several of them import their
# subject as a bare module name. Putting the subject directories on
# PYTHONPATH keeps that working without scattering sys.path edits through
# every test file, and lets the suite run from a plain checkout with nothing
# installed.
IMPORT_DIRS = ("src", "tools", "tools/migrate", "examples")
ADDED_FILES = (
    "tools/verify.py",
    "tests/test_cli.py", "tests/test_e2e.py", "tests/test_install.py",
    "tests/test_migrations.py", "tests/test_run_demo.py",
    "tests/test_synthetic_benchmark.py",
)


def _env(root):
    existing = os.environ.get("PYTHONPATH")
    parts = [str(root / d) for d in IMPORT_DIRS]
    if existing:
        parts.append(existing)
    return dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
                PYTHONPATH=os.pathsep.join(parts))


def run_checks(root):
    env = _env(root)
    for directory in ("src", "tools", "examples"):
        for path in sorted((root / directory).rglob("*.py")):
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path),
                      feature_version=(3, 10))
    subprocess.run(
        [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests",
         "-p", "test_*.py", "-v"], cwd=root, env=env, check=True)
    subprocess.run([sys.executable, "-B", "-m", "oldhand.cli", "selftest"],
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
    with tempfile.TemporaryDirectory(prefix="oldhand-verify-") as temporary:
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
