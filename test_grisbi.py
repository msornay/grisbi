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


def run_grisbi_split(*args, stdin_text="", env_extra=None, cwd=None):
    """Run grisbi.py, return (returncode, stdout, stderr) separately."""
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
    return proc.returncode, proc.stdout, proc.stderr


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
            self.test_folder_empty_suggests_path()
            self.test_folder_empty_hint()
            self.test_env_var_expansion()
            self.test_env_var_home_expansion()
            self.test_env_var_in_folder_directive()
            self.test_check_command()
            self.test_check_no_valid_dirs()
            self.test_folder_only_no_subdirs()
            self.test_directory_directive()
            self.test_directory_directive_mixed()
            self.test_prune_missing_arg()
            self.test_prune_non_numeric()
            self.test_prune_zero_days()
            self.test_prune_deletes_old_keeps_recent()
            self.test_prune_empty_dir()
            self.test_prune_unparseable_timestamp()
            self.test_restore_missing_arg()
            self.test_restore_nonexistent_file()
            self.test_restore_round_trip()
            self.test_backup_with_age_passphrase_env()
            self.test_restore_with_age_passphrase_env()
            self.test_no_duplicate_error_messages()
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
        Path(self.home, ".grisbirc").write_text(
            "# comment\npath ~/testdata\npath ~/nonexistent\n"
        )

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

        Path(self.home, ".grisbirc").write_text("~/testdata\npath ~/notes\n")

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
            self.fail(
                f"expected alpha and beta archives, got: {list(outdir.glob('*'))}"
            )

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
        Path(self.home, ".grisbirc").write_text(
            "path ~/testdata\nfolder ~/emptyparent\n"
        )

        outdir = Path(self.tmpdir, "output_folder_empty")
        outdir.mkdir()

        rc, output = run_grisbi(stdin_text="secret\nsecret\n", cwd=str(outdir))
        if "no subdirectories" in output:
            self.ok("folder empty dir warning")
        else:
            self.fail(f"expected subdirectory warning: {output}")

    def test_folder_empty_suggests_path(self):
        print("-- folder empty dir suggests path")
        emptyparent = Path(self.home, "emptyparent2")
        emptyparent.mkdir()
        (emptyparent / "file.txt").write_text("not a dir")

        testdata = Path(self.home, "testdata")
        testdata.mkdir(exist_ok=True)
        Path(self.home, ".grisbirc").write_text(
            "path ~/testdata\nfolder ~/emptyparent2\n"
        )

        outdir = Path(self.tmpdir, "output_folder_suggest")
        outdir.mkdir()

        rc, output = run_grisbi(stdin_text="secret\nsecret\n", cwd=str(outdir))
        if "use 'path" in output.lower() or "instead of 'folder'" in output:
            self.ok("folder empty suggests using path")
        else:
            self.fail(f"expected path suggestion: {output}")

    def test_folder_empty_hint(self):
        print("-- folder empty dir shows hint to use path")
        emptyparent = Path(self.home, "emptyparent3")
        emptyparent.mkdir()
        (emptyparent / "file.txt").write_text("not a dir")

        testdata = Path(self.home, "testdata")
        testdata.mkdir(exist_ok=True)
        Path(self.home, ".grisbirc").write_text(
            "path ~/testdata\nfolder ~/emptyparent3\n"
        )

        outdir = Path(self.tmpdir, "output_folder_hint")
        outdir.mkdir()

        rc, output = run_grisbi(stdin_text="secret\nsecret\n", cwd=str(outdir))
        if "Hint" in output and "path" in output:
            self.ok("folder empty dir shows hint to use path directive")
        else:
            self.fail(f"expected hint message: {output}")

    # --- Environment variable expansion tests ---

    def test_env_var_expansion(self):
        print("-- $VAR expansion in paths")
        testdata = Path(self.home, "mydata")
        testdata.mkdir(exist_ok=True)
        (testdata / "file.txt").write_text("hello")

        Path(self.home, ".grisbirc").write_text("path $GRISBI_TEST_DIR\n")

        outdir = Path(self.tmpdir, "output_envvar")
        outdir.mkdir()

        rc, output = run_grisbi(
            stdin_text="secret\nsecret\n",
            cwd=str(outdir),
            env_extra={"GRISBI_TEST_DIR": str(testdata)},
        )
        if "1 archive(s) created" in output:
            self.ok("$VAR expansion works in path directive")
        else:
            self.fail(f"env var expansion failed: {output}")

    def test_env_var_home_expansion(self):
        print("-- $HOME expansion in paths")
        testdata = Path(self.home, "testdata")
        testdata.mkdir(exist_ok=True)
        (testdata / "file.txt").write_text("hello")

        Path(self.home, ".grisbirc").write_text("path $HOME/testdata\n")

        outdir = Path(self.tmpdir, "output_envhome")
        outdir.mkdir()

        rc, output = run_grisbi(stdin_text="secret\nsecret\n", cwd=str(outdir))
        if "1 archive(s) created" in output:
            self.ok("$HOME expansion works")
        else:
            self.fail(f"$HOME expansion failed: {output}")

    def test_env_var_in_folder_directive(self):
        print("-- $VAR expansion in folder directive")
        parent = Path(self.home, "envprojects")
        parent.mkdir()
        (parent / "proj1").mkdir()
        (parent / "proj1" / "f.txt").write_text("content")
        (parent / "proj2").mkdir()
        (parent / "proj2" / "f.txt").write_text("content")

        Path(self.home, ".grisbirc").write_text("folder $GRISBI_FOLDER\n")

        outdir = Path(self.tmpdir, "output_envfolder")
        outdir.mkdir()

        rc, output = run_grisbi(
            stdin_text="secret\nsecret\n",
            cwd=str(outdir),
            env_extra={"GRISBI_FOLDER": str(parent)},
        )
        if "2 archive(s) created" in output:
            self.ok("$VAR expansion works in folder directive")
        else:
            self.fail(f"env var in folder failed: {output}")

    # --- Check command tests ---

    def test_check_command(self):
        print("-- check command")
        testdata = Path(self.home, "testdata")
        testdata.mkdir(exist_ok=True)
        (testdata / "file.txt").write_text("hello")
        notes = Path(self.home, "notes")
        notes.mkdir(exist_ok=True)

        Path(self.home, ".grisbirc").write_text("path ~/testdata\npath ~/notes\n")

        rc, output = run_grisbi("--check")
        if rc == 0 and "Directories to back up (2)" in output:
            self.ok("check shows directory count")
        else:
            self.fail(f"check failed: rc={rc}, output={output}")
        if "testdata" in output and "notes" in output:
            self.ok("check lists directories")
        else:
            self.fail(f"check missing dirs: {output}")

    def test_check_no_valid_dirs(self):
        print("-- check with no valid dirs")
        Path(self.home, ".grisbirc").write_text("path ~/nonexistent\n")

        rc, output = run_grisbi("--check")
        if rc != 0 and "No valid directories" in output:
            self.ok("check reports no valid directories")
        else:
            self.fail(f"expected error: rc={rc}, output={output}")

    def test_folder_only_no_subdirs(self):
        print("-- folder only config with no subdirs (common mistake)")
        flatdir = Path(self.home, "flatdir")
        flatdir.mkdir()
        (flatdir / "a.txt").write_text("a")
        (flatdir / "b.txt").write_text("b")

        Path(self.home, ".grisbirc").write_text("folder ~/flatdir\n")

        rc, output = run_grisbi("--check")
        if rc != 0:
            self.ok("folder-only with no subdirs fails as expected")
        else:
            self.fail(f"expected failure: rc={rc}, output={output}")
        if "Hint" in output:
            self.ok("shows actionable hint message")
        else:
            self.fail(f"expected hint: {output}")

    # --- Directory directive tests ---

    def test_directory_directive(self):
        print("-- directory directive (alias for path)")
        testdata = Path(self.home, "testdata")
        testdata.mkdir(exist_ok=True)
        (testdata / "file.txt").write_text("hello")
        Path(self.home, ".grisbirc").write_text("directory ~/testdata\n")

        outdir = Path(self.tmpdir, "output_directory")
        outdir.mkdir()

        rc, output = run_grisbi(stdin_text="secret\nsecret\n", cwd=str(outdir))
        if "1 archive(s) created" in output:
            self.ok("directory directive backs up directory")
        else:
            self.fail(f"directory directive failed: {output}")

    def test_directory_directive_mixed(self):
        print("-- directory directive mixed with path and folder")
        testdata = Path(self.home, "testdata")
        testdata.mkdir(exist_ok=True)
        (testdata / "file.txt").write_text("hello")
        notes = Path(self.home, "notes")
        notes.mkdir(exist_ok=True)
        (notes / "n.txt").write_text("note")

        Path(self.home, ".grisbirc").write_text("directory ~/testdata\npath ~/notes\n")

        outdir = Path(self.tmpdir, "output_directory_mixed")
        outdir.mkdir()

        rc, output = run_grisbi(stdin_text="secret\nsecret\n", cwd=str(outdir))
        if "2 archive(s) created" in output:
            self.ok("directory + path mixed works")
        else:
            self.fail(f"directory mixed failed: {output}")

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

    # --- AGE_PASSPHRASE env var tests ---

    def test_backup_with_age_passphrase_env(self):
        print("-- backup with AGE_PASSPHRASE env (no stdin)")
        testdata = Path(self.home, "testdata")
        testdata.mkdir(exist_ok=True)
        (testdata / "file.txt").write_text("hello")
        Path(self.home, ".grisbirc").write_text("path ~/testdata\n")

        outdir = Path(self.tmpdir, "output_env_backup")
        outdir.mkdir()

        rc, output = run_grisbi(
            stdin_text="",
            cwd=str(outdir),
            env_extra={"AGE_PASSPHRASE": "envsecret"},
        )
        if rc == 0 and "1 archive(s) created" in output:
            self.ok("backup succeeds with AGE_PASSPHRASE env")
        else:
            self.fail(f"env backup failed: rc={rc}, output={output}")

        if "Passphrase" not in output:
            self.ok("no passphrase prompt when AGE_PASSPHRASE set")
        else:
            self.fail(f"should not prompt: {output}")

        age_files = list(outdir.glob("testdata-*.tar.gz.age"))
        if age_files:
            self._env_backup_file = age_files[0]
        else:
            self.fail("no .age file created")
            self._env_backup_file = None

    def test_restore_with_age_passphrase_env(self):
        print("-- restore with AGE_PASSPHRASE env (no stdin)")
        if not hasattr(self, "_env_backup_file") or self._env_backup_file is None:
            self.fail("no backup file from previous test")
            return

        restore_dir = Path(self.tmpdir, "restored_env")
        restore_dir.mkdir()

        rc, output = run_grisbi(
            "--restore",
            str(self._env_backup_file),
            stdin_text="",
            cwd=str(restore_dir),
            env_extra={"AGE_PASSPHRASE": "envsecret"},
        )
        if "Restored from" in output:
            self.ok("restore succeeds with AGE_PASSPHRASE env")
        else:
            self.fail(f"env restore failed: rc={rc}, output={output}")

        if "Passphrase" not in output:
            self.ok("no passphrase prompt on restore")
        else:
            self.fail(f"should not prompt on restore: {output}")

        restored_file = restore_dir / "testdata" / "file.txt"
        if restored_file.exists() and restored_file.read_text() == "hello":
            self.ok("restored content matches via env passphrase")
        else:
            self.fail("restored file missing or wrong content")

    # --- Non-duplication tests ---

    def test_no_duplicate_error_messages(self):
        print("-- error messages not duplicated")
        # Remove config so missing-config error fires
        config = Path(self.home, ".grisbirc")
        if config.exists():
            config.unlink()

        cases = [
            ([], "not found", "missing config"),
            (["--restore"], "Usage", "restore missing arg"),
            (
                ["--restore", "/nonexistent.tar.gz.age"],
                "not found",
                "restore nonexistent",
            ),
            (["--prune"], "Usage", "prune missing arg"),
            (["--prune", "abc"], "Usage", "prune bad arg"),
            (["--prune", "0"], "Usage", "prune zero"),
        ]

        for args, expected_msg, label in cases:
            rc, stdout, stderr = run_grisbi_split(*args, stdin_text="x\nx\n")
            if stdout and expected_msg in stdout and expected_msg in stderr:
                self.fail(f"{label}: message in both stdout and stderr")
                continue
            combined = stdout + stderr
            count = combined.count(expected_msg)
            if count == 1:
                self.ok(f"{label}: message appears exactly once")
            elif count == 0:
                self.fail(f"{label}: expected '{expected_msg}' not found")
            else:
                self.fail(f"{label}: '{expected_msg}' appears {count} times")


if __name__ == "__main__":
    runner = TestRunner()
    runner.run()
