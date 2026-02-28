#!/usr/bin/env python3
"""grisbi — encrypted backup tool using age + tar."""

import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def expand_path(raw_path):
    """Expand ~ and environment variables in a path string."""
    return os.path.expandvars(os.path.expanduser(raw_path))


def parse_config(config_path):
    """Parse ~/.grisbirc and return list of (directive, expanded_path) tuples.

    Supported directives:
      path <dir>      — back up a single directory
      directory <dir> — alias for path
      folder <dir>    — back up each immediate child of <dir> as a separate archive
      <dir>           — bare path (no directive), treated as "path <dir>"
    """
    if not config_path.is_file():
        print(f"Error: {config_path} not found.", file=sys.stderr)
        sys.exit(1)

    entries = []
    for line in config_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^(path|directory|folder)\s+(.*)", stripped)
        if match:
            directive = match.group(1)
            if directive == "directory":
                directive = "path"
            raw_path = match.group(2).strip()
        else:
            # Bare path (no directive) treated as "path"
            directive = "path"
            raw_path = stripped
        expanded = expand_path(raw_path)
        entries.append((directive, expanded))

    if not entries:
        print(f"Error: no paths configured in {config_path}.", file=sys.stderr)
        sys.exit(1)

    return entries


def resolve_backup_dirs(entries):
    """Expand entries into a list of directories to back up.

    'path' entries are used as-is.
    'folder' entries expand to each immediate child directory.
    """
    dirs = []
    for directive, path_str in entries:
        p = Path(path_str)
        if directive == "path":
            if not p.is_dir():
                print(
                    f"Warning: path {p} is not a directory or does not exist, "
                    f"skipping.",
                    file=sys.stderr,
                )
                continue
            dirs.append(p)
        elif directive == "folder":
            if not p.is_dir():
                print(
                    f"Warning: folder {p} is not a directory or does not exist, "
                    f"skipping.",
                    file=sys.stderr,
                )
                continue
            children = sorted(child for child in p.iterdir() if child.is_dir())
            if not children:
                print(
                    f"Warning: folder {p} has no subdirectories, skipping. "
                    f"(Hint: use 'path {path_str}' to back up the directory itself.)",
                    file=sys.stderr,
                )
            dirs.extend(children)
    return dirs


def has_batchpass():
    """Check if age-plugin-batchpass is available."""
    try:
        subprocess.run(
            ["age-plugin-batchpass", "--help"],
            capture_output=True,
            check=False,
        )
        return True
    except FileNotFoundError:
        return False


def age_encrypt(tar_data, outfile, use_batchpass):
    """Encrypt tar data with age, writing to outfile."""
    if use_batchpass:
        proc = subprocess.run(
            ["age", "-e", "-j", "batchpass", "-o", str(outfile)],
            input=tar_data,
            capture_output=True,
        )
    else:
        # Fall back to -p with temp file (requires TTY)
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(tar_data)
            tmp_path = tmp.name
        try:
            proc = subprocess.run(
                ["age", "-e", "-p", "-o", str(outfile), tmp_path],
                stdin=open("/dev/tty"),
                capture_output=True,
            )
        finally:
            os.unlink(tmp_path)

    if proc.returncode != 0:
        print(f"Error: age encryption failed: {proc.stderr.decode()}", file=sys.stderr)
        sys.exit(1)


def age_decrypt(infile, use_batchpass):
    """Decrypt an age file, returning the plaintext bytes."""
    if use_batchpass:
        proc = subprocess.run(
            ["age", "-d", "-j", "batchpass", str(infile)],
            capture_output=True,
        )
    else:
        proc = subprocess.run(
            ["age", "-d", "-p", "-o", "-", str(infile)],
            stdin=open("/dev/tty"),
            capture_output=True,
        )

    if proc.returncode != 0:
        print(f"Error: age decryption failed: {proc.stderr.decode()}", file=sys.stderr)
        sys.exit(1)

    return proc.stdout


def cmd_check(config_path):
    """Validate config and show what would be backed up."""
    entries = parse_config(config_path)
    dirs = resolve_backup_dirs(entries)

    if not dirs:
        print("No valid directories to back up.", file=sys.stderr)
        sys.exit(1)

    print(f"Config: {config_path}")
    print(f"Directories to back up ({len(dirs)}):")
    for d in dirs:
        print(f"  {d}")


def cmd_backup(config_path):
    """Back up directories listed in config."""
    entries = parse_config(config_path)
    dirs = resolve_backup_dirs(entries)

    if not dirs:
        print("Error: no valid directories to back up.", file=sys.stderr)
        sys.exit(1)

    # Use AGE_PASSPHRASE from environment if set, otherwise prompt
    passphrase = os.environ.get("AGE_PASSPHRASE")
    if not passphrase:
        passphrase = input_passphrase("Passphrase: ")
        confirm = input_passphrase("Confirm: ")
        print()

        if passphrase != confirm:
            print("Error: passphrases do not match.", file=sys.stderr)
            sys.exit(1)

        os.environ["AGE_PASSPHRASE"] = passphrase
    use_bp = has_batchpass()

    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    count = 0
    total_size = 0

    for d in dirs:
        parent = str(d.parent)
        base = d.name
        outfile = Path(f"./{base}-{timestamp}.tar.gz.age")

        tar_proc = subprocess.run(
            ["tar", "cz", "-C", parent, base],
            capture_output=True,
        )
        if tar_proc.returncode != 0:
            print(
                f"Warning: tar failed for {d}: {tar_proc.stderr.decode()}",
                file=sys.stderr,
            )
            continue

        age_encrypt(tar_proc.stdout, outfile, use_bp)
        size = outfile.stat().st_size
        print(f"./{outfile.name} ({size} bytes)")
        count += 1
        total_size += size

    print(f"{count} archive(s) created, total size: {total_size} bytes")


def cmd_restore(filepath=None):
    """Restore from an encrypted archive."""
    if filepath is None:
        print("Usage: grisbi --restore <file.tar.gz.age>", file=sys.stderr)
        sys.exit(1)
    p = Path(filepath)
    if not p.is_file():
        print(f"Error: {filepath} not found.", file=sys.stderr)
        sys.exit(1)

    passphrase = os.environ.get("AGE_PASSPHRASE")
    if not passphrase:
        passphrase = input_passphrase("Passphrase: ")
        print()
        os.environ["AGE_PASSPHRASE"] = passphrase

    use_bp = has_batchpass()
    plaintext = age_decrypt(p, use_bp)

    tar_proc = subprocess.run(
        ["tar", "xz"],
        input=plaintext,
        capture_output=True,
    )
    if tar_proc.returncode != 0:
        print(
            f"Error: tar extraction failed: {tar_proc.stderr.decode()}", file=sys.stderr
        )
        sys.exit(1)

    print(f"Restored from {filepath}")


def cmd_prune(days_str=None):
    """Delete .tar.gz.age backups older than N days."""
    if days_str is None or not days_str.isdigit() or int(days_str) == 0:
        print("Usage: grisbi --prune <days>", file=sys.stderr)
        print(
            "Delete .tar.gz.age backups in the current directory older than <days> days.",
            file=sys.stderr,
        )
        sys.exit(1)

    max_age_days = int(days_str)
    now = datetime.now()
    ts_pattern = re.compile(r"-(\d{4}-\d{2}-\d{2}-\d{6})\.tar\.gz\.age$")

    count = 0
    freed = 0

    for f in sorted(Path(".").glob("*.tar.gz.age")):
        m = ts_pattern.search(f.name)
        if not m:
            continue

        ts_str = m.group(1)
        try:
            file_dt = datetime.strptime(ts_str, "%Y-%m-%d-%H%M%S")
        except ValueError:
            print(
                f"Warning: cannot parse timestamp in {f.name}, skipping.",
                file=sys.stderr,
            )
            continue

        age_days = (now - file_dt).total_seconds() / 86400
        if age_days > max_age_days:
            size = f.stat().st_size
            f.unlink()
            print(f"Deleted {f.name} ({size} bytes)")
            count += 1
            freed += size

    print(f"{count} archive(s) deleted, {freed} bytes freed")


def input_passphrase(prompt):
    """Read passphrase from stdin (supports both TTY and pipe)."""
    if sys.stdin.isatty():
        import getpass

        return getpass.getpass(prompt)
    else:
        # When piped, read a line from stdin
        sys.stderr.write(prompt)
        return sys.stdin.readline().rstrip("\n")


def main():
    args = sys.argv[1:]

    if args and args[0] == "--restore":
        cmd_restore(args[1] if len(args) >= 2 else None)
    elif args and args[0] == "--prune":
        cmd_prune(args[1] if len(args) >= 2 else None)
    elif args and args[0] == "--check":
        config_path = Path.home() / ".grisbirc"
        cmd_check(config_path)
    else:
        config_path = Path.home() / ".grisbirc"
        cmd_backup(config_path)


if __name__ == "__main__":
    main()
