import contextlib
import io
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import install


POSIX_ONLY = unittest.skipIf(
    os.name == "nt",
    "Exercises POSIX shell-profile quoting or symlink semantics that Windows "
    "has no analogue for: NTFS cannot represent these filenames, and symlink "
    "creation needs elevation. Windows PATH handling is covered separately by "
    "WindowsEnvironmentTests.")


class InstallTestCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.bin_dir = self.home / ".local" / "bin"
        self.bin_dir.mkdir(parents=True)
        self.archive = self.home / "archive"
        (self.archive / "memory").mkdir(parents=True)
        self.rc = self.home / ".zshrc"
        self.start_patch(mock.patch.dict(os.environ, {
            "HOME": str(self.home),
            "USERPROFILE": str(self.home),
            "PATH": str(self.bin_dir),
            "SHELL": "/bin/zsh",
        }, clear=True))
        self.start_patch(mock.patch.object(install, "IS_WINDOWS", False))
        self.run = self.start_patch(mock.patch.object(
            install.subprocess, "run",
            return_value=subprocess.CompletedProcess([], 0, "archive ready\n", "")))

    def start_patch(self, patcher):
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    def invoke(self, *args):
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        with mock.patch.object(sys, "argv", ["install.py", *map(str, args)]):
            with contextlib.redirect_stdout(self.stdout), contextlib.redirect_stderr(self.stderr):
                return install.main()


class LauncherCollisionTests(InstallTestCase):
    def test_unrelated_launcher_is_preserved(self):
        for windows in (False, True):
            with self.subTest(windows=windows), mock.patch.object(install, "IS_WINDOWS", windows):
                target = self.bin_dir / ("oldhand.cmd" if windows else "oldhand")
                target.write_bytes(b"unrelated command\xff\n")
                self.rc.write_text("user profile\n", encoding="utf-8")
                self.assertEqual(self.invoke(self.archive, "--shell-rc"), 1)
                self.assertEqual(target.read_bytes(), b"unrelated command\xff\n")
                self.assertEqual(self.rc.read_text(), "user profile\n")
                self.assertIn("Refusing", self.stderr.getvalue())
                self.run.assert_not_called()

    @POSIX_ONLY
    def test_symlinks_are_preserved_even_when_owned_or_dangling(self):
        for windows in (False, True):
            with mock.patch.object(install, "IS_WINDOWS", windows):
                source = install.write_launcher(self.home / "other")
                target = self.bin_dir / source.name
                for destination in (source, self.home / "missing"):
                    with self.subTest(windows=windows, destination=destination):
                        target.symlink_to(destination)
                        before = source.read_bytes()
                        self.assertEqual(self.invoke(self.archive), 1)
                        self.assertTrue(target.is_symlink())
                        self.assertEqual(target.readlink(), destination)
                        self.assertEqual(source.read_bytes(), before)
                        self.assertFalse((self.home / "missing").exists())
                        target.unlink()
        self.run.assert_not_called()

    def test_directory_collision_is_preserved(self):
        target = self.bin_dir / "oldhand"
        target.mkdir()
        self.assertEqual(self.invoke(self.archive), 1)
        self.assertTrue(target.is_dir())
        self.run.assert_not_called()

    def test_owned_launcher_can_be_reinstalled(self):
        for windows in (False, True):
            with self.subTest(windows=windows), mock.patch.object(install, "IS_WINDOWS", windows):
                target = install.write_launcher(self.bin_dir)
                with mock.patch.object(sys, "executable", "/new/python"):
                    self.assertEqual(self.invoke(self.archive), 0)
                self.assertIn("/new/python", target.read_text())


class LauncherUninstallTests(InstallTestCase):
    def test_uninstall_preserves_unrelated_launchers(self):
        for windows in (False, True):
            with mock.patch.object(install, "IS_WINDOWS", windows):
                target = self.bin_dir / ("oldhand.cmd" if windows else "oldhand")
                for content in (b"unrelated\xff\n", b"echo Written by tools/install.py.\n"):
                    with self.subTest(windows=windows, content=content):
                        target.write_bytes(content)
                        self.assertEqual(self.invoke("--uninstall"), 0)
                        self.assertTrue(target.exists())
                        self.assertEqual(target.read_bytes(), content)

    @POSIX_ONLY
    def test_uninstall_preserves_symlinks_and_their_targets(self):
        for windows in (False, True):
            with mock.patch.object(install, "IS_WINDOWS", windows):
                source = install.write_launcher(self.home / "other")
                target = self.bin_dir / source.name
                for destination in (source, self.home / "missing"):
                    with self.subTest(windows=windows, destination=destination):
                        target.symlink_to(destination)
                        before = source.read_bytes()
                        self.assertEqual(self.invoke("--uninstall"), 0)
                        self.assertTrue(target.is_symlink())
                        self.assertEqual(target.readlink(), destination)
                        self.assertEqual(source.read_bytes(), before)
                        target.unlink()

    def test_uninstall_preserves_directory(self):
        target = self.bin_dir / "oldhand"
        target.mkdir()
        self.assertEqual(self.invoke("--uninstall"), 0)
        self.assertTrue(target.is_dir())

    def test_uninstall_removes_owned_launcher_and_is_repeatable(self):
        for windows in (False, True):
            with self.subTest(windows=windows), mock.patch.object(install, "IS_WINDOWS", windows):
                target = install.write_launcher(self.bin_dir)
                self.assertEqual(self.invoke("--uninstall"), 0)
                self.assertFalse(target.exists())
                self.assertEqual(self.invoke("--uninstall"), 0)
                self.assertTrue((self.archive / "memory").is_dir())


class ProfileUninstallTests(InstallTestCase):
    def test_only_owned_assignments_are_removed(self):
        unowned = (
            'export OLDHAND_ROOT="/user/archive"\r\n'
            'alias show_root=\'echo "$OLDHAND_ROOT"\'\n'
            f'echo "{install.MARKER}"\n'
            f'{install.MARKER}\n'
            f'export OTHER="value"  {install.MARKER}\n'
            f'export OLDHAND_ROOT="/user"; echo keep  {install.MARKER}\n'
            f'export OLDHAND_ROOT="/user"  {install.MARKER} extra\n'
            f'export OLDHAND_ROOT="literal {install.MARKER}"\n'
            'last line without newline')
        owned = f'export OLDHAND_ROOT="/old/archive"  {install.MARKER}\r\n'
        self.rc.write_bytes((owned + unowned).encode())
        self.assertEqual(self.invoke("--uninstall"), 0)
        self.assertEqual(self.rc.read_bytes(), unowned.encode())
        self.run.assert_not_called()

    def test_shell_commands_with_marker_are_not_owned(self):
        content = (
            f'export OLDHAND_ROOT=/user;true  {install.MARKER}\n'
            f'export OLDHAND_ROOT=$(pwd)  {install.MARKER}\n'
            f'export OLDHAND_ROOT="/user";true  {install.MARKER}\n').encode()
        self.rc.write_bytes(content)
        self.assertEqual(self.invoke("--uninstall"), 0)
        self.assertEqual(self.rc.read_bytes(), content)

    def test_profile_without_owned_assignment_is_unchanged(self):
        content = f'echo OLDHAND_ROOT\r\n{install.MARKER}\r\nlast'.encode()
        self.rc.write_bytes(content)
        self.assertEqual(self.invoke("--uninstall"), 0)
        self.assertEqual(self.rc.read_bytes(), content)

    def test_multiple_owned_assignments_and_no_final_newline(self):
        owned = f'export OLDHAND_ROOT="/old"  {install.MARKER}'
        self.rc.write_text(owned + '\nkeep\n' + owned, encoding="utf-8")
        self.assertEqual(self.invoke("--uninstall"), 0)
        self.assertEqual(self.rc.read_bytes(), b'keep\n')
        self.assertEqual(self.invoke("--uninstall"), 0)
        self.assertEqual(self.rc.read_bytes(), b'keep\n')


class ProfileReinstallTests(InstallTestCase):
    def test_reinstall_updates_owned_assignment_in_place(self):
        for eol in ("\n", "\r\n"):
            with self.subTest(eol=repr(eol)):
                content = f"top{eol}export OLDHAND_ROOT=\"/old\"  {install.MARKER}{eol}bottom"
                self.rc.write_bytes(content.encode())
                self.assertEqual(self.invoke(self.archive, "--shell-rc"), 0)
                result = self.rc.read_bytes()
                self.assertEqual(result.count(b"export OLDHAND_ROOT="), 1)
                self.assertNotIn(b"/old", result)
                self.assertIn(str(self.archive).encode(), result)
                self.assertIn(install.MARKER.encode(), result)
                self.assertIn(b"top", result)
                self.assertIn(b"bottom", result)
                self.assertIn(eol.encode(), result)

    def test_reinstall_without_shell_rc_leaves_profile_alone(self):
        content = f'export OLDHAND_ROOT="/old"  {install.MARKER}\n'.encode()
        self.rc.write_bytes(content)
        self.assertEqual(self.invoke(self.archive), 0)
        self.assertEqual(self.rc.read_bytes(), content)

    def test_reinstall_is_idempotent_and_never_duplicates(self):
        self.assertEqual(self.invoke(self.archive, "--shell-rc"), 0)
        first = self.rc.read_bytes()
        self.assertEqual(self.invoke(self.archive, "--shell-rc"), 0)
        self.assertEqual(self.rc.read_bytes(), first)
        other = self.home / "second"
        (other / "memory").mkdir(parents=True)
        self.assertEqual(self.invoke(other, "--shell-rc"), 0)
        result = self.rc.read_bytes()
        self.assertEqual(result.count(b"export OLDHAND_ROOT="), 1)
        self.assertIn(str(other.resolve()).encode(), result)

    def test_reinstall_appends_owned_line_beside_unowned_ones(self):
        content = f'export OLDHAND_ROOT="/user/archive"\nkeep  {install.MARKER}\n'.encode()
        self.rc.write_bytes(content)
        self.assertEqual(self.invoke(self.archive, "--shell-rc"), 0)
        result = self.rc.read_bytes()
        self.assertIn(b'export OLDHAND_ROOT="/user/archive"', result)
        self.assertIn(b"keep  " + install.MARKER.encode(), result)
        self.assertEqual(result.count(b"export OLDHAND_ROOT="), 2)


class FishProfileTests(InstallTestCase):
    def setUp(self):
        super().setUp()
        self.start_patch(mock.patch.dict(os.environ, {"SHELL": "/usr/bin/fish"}, clear=False))
        self.rc = self.home / ".config" / "fish" / "config.fish"

    def test_fish_profile_uses_set_and_roundtrips_through_reinstall_and_uninstall(self):
        archive = self.home / "quo'te\\path"
        (archive / "memory").mkdir(parents=True)
        self.assertEqual(self.invoke(archive, "--shell-rc"), 0)
        first = self.rc.read_text(encoding="utf-8")
        expected = f"set -gx OLDHAND_ROOT {install.fish_quote(str(archive.resolve()))}"
        self.assertIn(expected, first)
        self.assertNotIn("export OLDHAND_ROOT=", first)

        self.assertEqual(self.invoke(archive, "--shell-rc"), 0)
        self.assertEqual(self.rc.read_text(encoding="utf-8"), first)
        self.assertEqual(self.invoke("--uninstall"), 0)
        self.assertNotIn("OLDHAND_ROOT", self.rc.read_text(encoding="utf-8"))

    def test_fish_reinstall_replaces_the_previous_owned_line(self):
        first = self.home / "first"
        second = self.home / "second"
        (first / "memory").mkdir(parents=True)
        (second / "memory").mkdir(parents=True)
        self.assertEqual(self.invoke(first, "--shell-rc"), 0)
        self.assertEqual(self.invoke(second, "--shell-rc"), 0)
        result = self.rc.read_text(encoding="utf-8")
        self.assertEqual(result.count("set -gx OLDHAND_ROOT "), 1)
        self.assertNotIn(str(first.resolve()), result)
        self.assertIn(str(second.resolve()), result)


class QuotingTests(InstallTestCase):
    def test_launcher_quotes_executable_and_script_paths(self):
        for windows in (False, True):
            with mock.patch.object(install, "IS_WINDOWS", windows):
                target = install.write_launcher(self.bin_dir)
                body = target.read_text()
                if windows:
                    self.assertIn(f'"{install.sys.executable}"', body)
                    self.assertIn(f'"{install.SRC_DIR}"', body)
                    self.assertIn("-m oldhand.cli", body)
                else:
                    argv = shlex.split(body.splitlines()[-1])
                    self.assertEqual(argv[0], f"PYTHONPATH={install.SRC_DIR}")
                    self.assertEqual(argv[1], "exec")
                    self.assertEqual(argv[2], install.sys.executable)
                    self.assertEqual(argv[3:5], ["-m", "oldhand.cli"])
                    self.assertEqual(argv[5], "$@")

    def test_launcher_source_path_with_special_characters(self):
        spaces = self.home / "pro gram files"
        spaces.mkdir()
        source = spaces / "sr c"
        with mock.patch.object(install, "SRC_DIR", source):
            target = install.write_launcher(self.bin_dir)
            body = target.read_text()
            self.assertIn(install.sh_quote(source), body)
            argv = shlex.split(body.splitlines()[-1])
            self.assertEqual(len(argv), 6)
            self.assertEqual(argv[0], f"PYTHONPATH={source}")

    def test_launcher_executable_with_quote_characters(self):
        tricky = str(self.home / "we'ird\"py" / "python")
        with mock.patch.object(sys, "executable", tricky):
            target = install.write_launcher(self.bin_dir)
            body = target.read_text()
            self.assertIn(install.sh_quote(tricky), body)
            argv = shlex.split(body.splitlines()[-1])
            self.assertEqual(len(argv), 6)
            self.assertEqual(argv[2], tricky)

    @POSIX_ONLY
    def test_launcher_handles_backslash_newline_and_glob_chars(self):
        tricky = str(self.home / "back\\slash")
        with mock.patch.object(sys, "executable", tricky):
            target = install.write_launcher(self.bin_dir)
            body = target.read_text()
            self.assertIn(install.sh_quote(tricky), body)
            argv = shlex.split(body.splitlines()[-1])
            self.assertEqual(argv[2], tricky)

    @POSIX_ONLY
    def test_profile_roundtrip_with_combined_quotes_spaces_and_newlines(self):
        for name in ("quo'te space", "quo'te\nline", "two' spaced 'quotes"):
            with self.subTest(name=name):
                archive = self.home / name
                (archive / "memory").mkdir(parents=True)
                self.rc.write_bytes(b"keep\r\n")
                self.assertEqual(self.invoke(archive, "--shell-rc"), 0)
                first = self.rc.read_bytes()
                self.assertEqual(self.invoke(archive, "--shell-rc"), 0)
                self.assertEqual(self.rc.read_bytes(), first)
                self.assertEqual(self.invoke("--uninstall"), 0)
                self.assertEqual(self.rc.read_bytes(), b"keep\r\n\n")

    @POSIX_ONLY
    def test_profile_line_quotes_archive_paths(self):
        for name in ('sp ace', "quo'te", 'dq"uote', 'back\\slash', 'star*glob'):
            with self.subTest(name=name):
                archive = self.home / name
                (archive / "memory").mkdir(parents=True)
                self.assertEqual(self.invoke(archive, "--shell-rc"), 0)
                text = self.rc.read_text()
                self.assertIn(
                    f"export OLDHAND_ROOT={install.sh_quote(str(archive.resolve()))}", text)
                self.assertNotIn(f"export OLDHAND_ROOT={archive.resolve()}", text)
                self.assertEqual(text.count("export OLDHAND_ROOT="), 1)

    @POSIX_ONLY
    def test_profile_line_parses_back_with_shlex(self):
        for name in ('sp ace', "quo'te", 'dq"uote', 'back\\slash', 'dollar$x', 'star*'):
            with self.subTest(name=name):
                archive = self.home / name
                (archive / "memory").mkdir(parents=True)
                self.assertEqual(self.invoke(archive, "--shell-rc"), 0)
                line = [l for l in self.rc.read_text().splitlines()
                        if "export OLDHAND_ROOT=" in l][-1]
                key, value = shlex.split(line)[1].split("=", 1)
                self.assertEqual(key, "OLDHAND_ROOT")
                self.assertEqual(value, str(archive.resolve()))


class WindowsEnvironmentTests(InstallTestCase):
    def test_failed_setx_fails_install_without_claiming_success(self):
        failed = subprocess.CompletedProcess([], 1, "", "access denied")
        with mock.patch.object(install, "IS_WINDOWS", True), \
                mock.patch.object(install.subprocess, "run", return_value=failed):
            self.assertEqual(self.invoke(self.archive), 1)
        self.assertTrue((self.bin_dir / "oldhand.cmd").exists())
        self.assertIn("Could not set OLDHAND_ROOT", self.stderr.getvalue())
        self.assertNotIn("(user environment)", self.stdout.getvalue())

    def test_failed_reg_delete_fails_uninstall_without_claiming_success(self):
        target = self.bin_dir / "oldhand.cmd"
        with mock.patch.object(install, "IS_WINDOWS", True):
            install.write_launcher(self.bin_dir)
        failed = subprocess.CompletedProcess([], 1, "", "access denied")
        with mock.patch.object(install, "IS_WINDOWS", True), \
                mock.patch.object(install.subprocess, "run", return_value=failed):
            self.assertEqual(self.invoke("--uninstall"), 1)
        self.assertFalse(target.exists())
        self.assertIn("Could not remove OLDHAND_ROOT", self.stderr.getvalue())
        self.assertNotIn("OLDHAND_ROOT (user environment)", self.stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
