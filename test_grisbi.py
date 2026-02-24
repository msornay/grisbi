#!/usr/bin/env python3
"""Tests for grisbi.py — encrypted backup tool."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).parent / "grisbi.py"


def check_prereqs():
    """Skip tests if age or age-plugin-batchpass not installed."""
    if shutil.which("age") is None:
        print("SKIP: age not installed", file=sys.stderr)
        sys.exit(0)
    if shutil.which("age-plugin-batchpass") is None:
        print(
            "SKIP: age-plugin-batchpass not installed "
            "(go install filippo.io/age/cmd/age-plugin-batchpass@latest)",
            file=sys.stderr,
        )
        sys.exit(0)


def run_grisbi(*args, stdin_text="", env_extra=None, cwd=None):
    """Run grisbi.py with given args, return (returncode, stdout+stderr)."""
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)] + list(args),
        input=stdin_text,
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
    )
    return proc.returncode, proc.stdout + proc.stderr


class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tmpdir = None
        self.home = None

    def setup(self):
        self.tmpdir = tempfile.mkdtemp()
        self.home = self.tmpdir
        os.environ["HOME"] = self.home

    def teardown(self):
        if self.tmpdir:
            shutil.rmtree(self.tmpdir)

    def ok(self, msg):
        self.passed += 1
        print(f"  ok: {msg}")

    def fail(self, msg):
        self.failed += 1
        print(f"  FAIL: {msg}", file=sys.stderr)

    def run(self):
        check_prereqs()
        self.setup()
        try:
            print("=== grisbi.py tests ===")
            self.test_missing_config()
            self.test_empty_config()
            self.test_mismatched_passphrase()
            self.test_successful_backup()
            self.test_round_trip_decrypt()
            self.test_nonexistent_path_warning()
            self.test_config_parsing()
            self.test_bare_path()
            self.test_bare_path_mixed()
            self.test_folder_directive()
            self.test_folder_nonexistent()
            self.test_folder_empty()
            self.test_prune_missing_arg()
            self.test_prune_non_numeric()
            self.test_prune_zero_days()
            self.test_prune_deletes_old_keeps_recent()
            self.test_prune_empty_dir()
            self.test_prune_unparseable_timestamp()
            self.test_restore_missing_arg()
            self.test_restore_nonexistent_file()
            self.test_restore_round_trip()
        finally:
            self.teardown()

        print()
        total = self.passed + self.failed
        print(f"{self.passed}/{total} tests passed")
        if self.failed > 0:
            sys.exit(1)

    # --- Config tests ---

    def test_missing_config(self):
        print("-- missing config")
        rc, output = run_grisbi(stdin_text="x\nx\n")
        if rc != 0 and "not found" in output:
            self.ok("missing config error")
        else:
            self.fail(f"unexpected: rc={rc}, output={output}")

    def test_empty_config(self):
        print("-- empty config")
        Path(self.home, ".grisbirc").touch()
        rc, output = run_grisbi(stdin_text="x\nx\n")
        if rc != 0 and "no paths configured" in output:
            self.ok("empty config error")
        else:
            self.fail(f"unexpected: rc={rc}, output={output}")

    # --- Passphrase tests ---

    def test_mismatched_passphrase(self):
        print("-- mismatched passphrase")
        testdata = Path(self.home, "testdata")
        testdata.mkdir(exist_ok=True)
        (testdata / "file.txt").write_text("hello")
        Path(self.home, ".grisbirc").write_text("path ~/testdata\n")

        rc, output = run_grisbi(stdin_text="abc\nxyz\n")
        if rc != 0 and "do not match" in output:
            self.ok("mismatched passphrase error")
        else:
            self.fail(f"unexpected: rc={rc}, output={output}")

    # --- Backup tests ---

    def test_successful_backup(self):
        print("-- successful backup")
        testdata = Path(self.home, "testdata")
        testdata.mkdir(exist_ok=True)
        (testdata / "file.txt").write_text("hello")
        Path(self.home, ".grisbirc").write_text("path ~/testdata\n")

        outdir = Path(self.tmpdir, "output")
        outdir.mkdir()

        rc, output = run_grisbi(stdin_text="secret\nsecret\n", cwd=str(outdir))
        if "1 archive(s) created" in output:
            self.ok("backup count")
        else:
            self.fail(f"unexpected output: {output}")

        age_files = list(outdir.glob("testdata-*.tar.gz.age"))
        if age_files:
            self.ok(f"age file created: {age_files[0].name}")
            self._backup_age_file = age_files[0]
        else:
            self.fail(f"no .age file found in {outdir}")
            self._backup_age_file = None

    def test_round_trip_decrypt(self):
        print("-- round-trip")
        if not hasattr(self, "_backup_age_file") or self._backup_age_file is None:
            self.fail("no backup file from previous test")
            return

        env = os.environ.copy()
        env["AGE_PASSPHRASE"] = "secret"
        proc = subprocess.run(
            ["age", "-d", "-j", "batchpass", str(self._backup_age_file)],
            capture_output=True,
            env=env,
        )
        tar_proc = subprocess.run(
            ["tar", "tz"],
            input=proc.stdout,
            capture_output=True,
        )
        if b"file.txt" in tar_proc.stdout:
            self.ok("round-trip decrypt lists file.txt")
        else:
            self.fail(f"round-trip decrypt failed: {tar_proc.stdout.decode()}")

    def test_nonexistent_path_warning(self):
        print("-- nonexistent path warning")
        Path(self.home, ".grisbirc").write_text("# comment\npath ~/testdata\npath ~/nonexistent\n")

        outdir = Path(self.tmpdir, "output2")
        outdir.mkdir()

        rc, output = run_grisbi(stdin_text="secret\nsecret\n", cwd=str(outdir))
        if "Warning" in output and "nonexistent" in output:
            self.ok("nonexistent path warning")
        else:
            self.fail(f"expected warning: {output}")
        if "1 archive(s) created" in output:
            self.ok("still backs up valid paths")
        else:
            self.fail(f"unexpected output: {output}")

    def test_config_parsing(self):
        print("-- config parsing")
        Path(self.home, ".grisbirc").write_text(
            "\n# this is a comment\npath ~/testdata\n   # indented comment\n\n"
        )

        outdir = Path(self.tmpdir, "output3")
        outdir.mkdir()

        rc, output = run_grisbi(stdin_text="secret\nsecret\n", cwd=str(outdir))
        if "1 archive(s) created" in output:
            self.ok("config with comments and blank lines")
        else:
            self.fail(f"config parsing failed: {output}")

    # --- Bare path tests ---

    def test_bare_path(self):
        print("-- bare path (no directive)")
        testdata = Path(self.home, "testdata")
        testdata.mkdir(exist_ok=True)
        (testdata / "file.txt").write_text("hello")
        Path(self.home, ".grisbirc").write_text("~/testdata\n")

        outdir = Path(self.tmpdir, "output_bare")
        outdir.mkdir()

        rc, output = run_grisbi(stdin_text="secret\nsecret\n", cwd=str(outdir))
        if "1 archive(s) created" in output:
            self.ok("bare path backs up directory")
        else:
            self.fail(f"bare path failed: {output}")

    def test_bare_path_mixed(self):
        print("-- bare path mixed with directives")
        testdata = Path(self.home, "testdata")
        testdata.mkdir(exist_ok=True)
        (testdata / "file.txt").write_text("hello")
        notes = Path(self.home, "notes")
        notes.mkdir(exist_ok=True)
        (notes / "n.txt").write_text("note")

        Path(self.home, ".grisbirc").write_text(
            "~/testdata\npath ~/notes\n"
        )

        outdir = Path(self.tmpdir, "output_bare_mixed")
        outdir.mkdir()

        rc, output = run_grisbi(stdin_text="secret\nsecret\n", cwd=str(outdir))
        if "2 archive(s) created" in output:
            self.ok("bare path works alongside path directive")
        else:
            self.fail(f"bare + path mixed failed: {output}")

    # --- Folder directive tests ---

    def test_folder_directive(self):
        print("-- folder directive")
        # Create a parent dir with two subdirectories
        parent = Path(self.home, "projects")
        parent.mkdir()
        (parent / "alpha").mkdir()
        (parent / "alpha" / "a.txt").write_text("alpha content")
        (parent / "beta").mkdir()
        (parent / "beta" / "b.txt").write_text("beta content")
        # Also create a regular file (should be ignored by folder)
        (parent / "readme.txt").write_text("not a dir")

        Path(self.home, ".grisbirc").write_text("folder ~/projects\n")

        outdir = Path(self.tmpdir, "output_folder")
        outdir.mkdir()

        rc, output = run_grisbi(stdin_text="secret\nsecret\n", cwd=str(outdir))
        if "2 archive(s) created" in output:
            self.ok("folder directive creates archives for each subdir")
        else:
            self.fail(f"expected 2 archives: {output}")

        alpha_files = list(outdir.glob("alpha-*.tar.gz.age"))
        beta_files = list(outdir.glob("beta-*.tar.gz.age"))
        if alpha_files and beta_files:
            self.ok("individual archives created for alpha and beta")
        else:
            self.fail(f"expected alpha and beta archives, got: {list(outdir.glob('*'))}")

    def test_folder_nonexistent(self):
        print("-- folder nonexistent dir")
        # folder directive with path+folder where folder target doesn't exist
        testdata = Path(self.home, "testdata")
        testdata.mkdir(exist_ok=True)
        (testdata / "file.txt").write_text("hello")
        Path(self.home, ".grisbirc").write_text("path ~/testdata\nfolder ~/nope\n")

        outdir = Path(self.tmpdir, "output_folder_noexist")
        outdir.mkdir()

        rc, output = run_grisbi(stdin_text="secret\nsecret\n", cwd=str(outdir))
        if "Warning" in output and "nope" in output:
            self.ok("folder nonexistent warning shown")
        else:
            self.fail(f"expected warning: {output}")
        if "1 archive(s) created" in output:
            self.ok("path directive still works alongside bad folder")
        else:
            self.fail(f"unexpected output: {output}")

    def test_folder_empty(self):
        print("-- folder empty dir")
        emptyparent = Path(self.home, "emptyparent")
        emptyparent.mkdir()
        # No subdirectories, only a file
        (emptyparent / "file.txt").write_text("not a dir")

        testdata = Path(self.home, "testdata")
        testdata.mkdir(exist_ok=True)
        Path(self.home, ".grisbirc").write_text("path ~/testdata\nfolder ~/emptyparent\n")

        outdir = Path(self.tmpdir, "output_folder_empty")
        outdir.mkdir()

        rc, output = run_grisbi(stdin_text="secret\nsecret\n", cwd=str(outdir))
        if "no subdirectories" in output:
            self.ok("folder empty dir warning")
        else:
            self.fail(f"expected subdirectory warning: {output}")

    # --- Prune tests ---

    def test_prune_missing_arg(self):
        print("-- prune: missing argument")
        rc, output = run_grisbi("--prune")
        if rc != 0 and "Usage" in output and "prune" in output:
            self.ok("prune missing arg shows usage")
        else:
            self.fail(f"unexpected: rc={rc}, output={output}")

    def test_prune_non_numeric(self):
        print("-- prune: non-numeric argument")
        rc, output = run_grisbi("--prune", "abc")
        if rc != 0 and "Usage" in output and "prune" in output:
            self.ok("prune non-numeric shows usage")
        else:
            self.fail(f"unexpected: rc={rc}, output={output}")

    def test_prune_zero_days(self):
        print("-- prune: zero days")
        rc, output = run_grisbi("--prune", "0")
        if rc != 0 and "Usage" in output and "prune" in output:
            self.ok("prune zero days shows usage")
        else:
            self.fail(f"unexpected: rc={rc}, output={output}")

    def test_prune_deletes_old_keeps_recent(self):
        print("-- prune: deletes old, keeps recent")
        prunedir = Path(self.tmpdir, "prunedir")
        prunedir.mkdir()
        (prunedir / "docs-2020-01-15-120000.tar.gz.age").touch()
        (prunedir / "docs-2020-06-01-080000.tar.gz.age").touch()
        (prunedir / "docs-2099-12-31-235959.tar.gz.age").touch()
        (prunedir / "notes-2020-03-10-090000.tar.gz.age").touch()
        (prunedir / "unrelated.txt").touch()

        rc, output = run_grisbi("--prune", "30", cwd=str(prunedir))
        if "3 archive(s) deleted" in output:
            self.ok("prune deleted 3 old archives")
        else:
            self.fail(f"expected 3 deletions: {output}")

        if (prunedir / "docs-2099-12-31-235959.tar.gz.age").exists():
            self.ok("prune kept recent archive")
        else:
            self.fail("prune should not have deleted recent archive")

        if (prunedir / "unrelated.txt").exists():
            self.ok("prune ignores non-.age files")
        else:
            self.fail("prune should not delete non-.age files")

    def test_prune_empty_dir(self):
        print("-- prune: empty directory")
        emptydir = Path(self.tmpdir, "emptydir")
        emptydir.mkdir()

        rc, output = run_grisbi("--prune", "7", cwd=str(emptydir))
        if "0 archive(s) deleted" in output:
            self.ok("prune in empty dir deletes nothing")
        else:
            self.fail(f"unexpected output: {output}")

    def test_prune_unparseable_timestamp(self):
        print("-- prune: unparseable timestamp")
        baddir = Path(self.tmpdir, "baddir")
        baddir.mkdir()
        (baddir / "docs-notadate.tar.gz.age").touch()
        (baddir / "docs-2020-01-15-120000.tar.gz.age").touch()

        rc, output = run_grisbi("--prune", "30", cwd=str(baddir))
        if "1 archive(s) deleted" in output:
            self.ok("prune skips unparseable, deletes valid old")
        else:
            self.fail(f"unexpected output: {output}")
        if (baddir / "docs-notadate.tar.gz.age").exists():
            self.ok("unparseable file kept")
        else:
            self.fail("unparseable file should not be deleted")

    # --- Restore tests ---

    def test_restore_missing_arg(self):
        print("-- restore missing argument")
        rc, output = run_grisbi("--restore")
        if rc != 0 and "Usage" in output:
            self.ok("restore usage error")
        else:
            self.fail(f"unexpected: rc={rc}, output={output}")

    def test_restore_nonexistent_file(self):
        print("-- restore nonexistent file")
        rc, output = run_grisbi("--restore", "/nonexistent.tar.gz.age")
        if rc != 0 and "not found" in output:
            self.ok("restore file not found error")
        else:
            self.fail(f"unexpected: rc={rc}, output={output}")

    def test_restore_round_trip(self):
        print("-- restore round-trip")
        if not hasattr(self, "_backup_age_file") or self._backup_age_file is None:
            self.fail("no backup file from previous test")
            return

        restore_dir = Path(self.tmpdir, "restored")
        restore_dir.mkdir()

        rc, output = run_grisbi(
            "--restore",
            str(self._backup_age_file),
            stdin_text="secret\n",
            cwd=str(restore_dir),
        )
        if "Restored from" in output:
            self.ok("restore success message")
        else:
            self.fail(f"unexpected restore output: {output}")

        restored_file = restore_dir / "testdata" / "file.txt"
        if restored_file.exists():
            content = restored_file.read_text()
            if content == "hello":
                self.ok("restored file content matches")
            else:
                self.fail(f"restored content mismatch: {content}")
        else:
            self.fail(f"restored file not found at {restored_file}")


if __name__ == "__main__":
    runner = TestRunner()
    runner.run()
