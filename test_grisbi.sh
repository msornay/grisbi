#!/usr/bin/env bash
set -euo pipefail

pass=0
fail=0

ok()   { pass=$((pass + 1)); echo "  ok: $1"; }
die()  { fail=$((fail + 1)); echo "  FAIL: $1" >&2; }

cleanup() { rm -rf "$TMPDIR_TEST"; }
trap cleanup EXIT

TMPDIR_TEST=$(mktemp -d)
export HOME="$TMPDIR_TEST"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GRISBI="$SCRIPT_DIR/grisbi.sh"

echo "=== grisbi tests ==="

# Check prerequisites
if ! command -v age >/dev/null 2>&1; then
  echo "SKIP: age not installed" >&2; exit 0
fi
if ! command -v age-plugin-batchpass >/dev/null 2>&1; then
  echo "SKIP: age-plugin-batchpass not installed (go install filippo.io/age/cmd/age-plugin-batchpass@latest)" >&2; exit 0
fi

# --- Test: missing config ---
echo "-- missing config"
if output=$(printf 'x\nx\n' | "$GRISBI" 2>&1); then
  die "should exit non-zero without config"
else
  if echo "$output" | grep -q "not found"; then
    ok "missing config error"
  else
    die "unexpected error: $output"
  fi
fi

# --- Test: empty config ---
echo "-- empty config"
touch "$HOME/.grisbirc"
if output=$(printf 'x\nx\n' | "$GRISBI" 2>&1); then
  die "should exit non-zero with empty config"
else
  if echo "$output" | grep -q "no paths configured"; then
    ok "empty config error"
  else
    die "unexpected error: $output"
  fi
fi

# --- Test: mismatched passphrase ---
echo "-- mismatched passphrase"
mkdir -p "$HOME/testdata"
echo "hello" > "$HOME/testdata/file.txt"
cat > "$HOME/.grisbirc" <<EOF
path ~/testdata
EOF
if output=$(printf 'abc\nxyz\n' | "$GRISBI" 2>&1); then
  die "should exit non-zero on mismatched passphrase"
else
  if echo "$output" | grep -q "do not match"; then
    ok "mismatched passphrase error"
  else
    die "unexpected error: $output"
  fi
fi

# --- Test: successful backup ---
echo "-- successful backup"
outdir="$TMPDIR_TEST/output"
mkdir -p "$outdir"
cd "$outdir"
output=$(printf 'secret\nsecret\n' | "$GRISBI" 2>&1)
if echo "$output" | grep -q "1 archive(s) created"; then
  ok "backup count"
else
  die "unexpected output: $output"
fi
age_file=$(ls "$outdir"/testdata-*.tar.gz.age 2>/dev/null | head -1)
if [[ -n "$age_file" ]]; then
  ok "age file created: $(basename "$age_file")"
else
  die "no .age file found in $outdir"
fi

# --- Test: round-trip decrypt ---
echo "-- round-trip"
if AGE_PASSPHRASE=secret age -d -j batchpass "$age_file" | tar tz | grep -q "file.txt"; then
  ok "round-trip decrypt lists file.txt"
else
  die "round-trip decrypt failed"
fi

# --- Test: nonexistent path warning ---
echo "-- nonexistent path warning"
cat > "$HOME/.grisbirc" <<EOF
# comment line
path ~/testdata
path ~/nonexistent
EOF
outdir2="$TMPDIR_TEST/output2"
mkdir -p "$outdir2"
cd "$outdir2"
output=$(printf 'secret\nsecret\n' | "$GRISBI" 2>&1)
if echo "$output" | grep -q "Warning.*nonexistent.*does not exist"; then
  ok "nonexistent path warning"
else
  die "expected warning for nonexistent path: $output"
fi
if echo "$output" | grep -q "1 archive(s) created"; then
  ok "still backs up valid paths"
else
  die "unexpected output: $output"
fi

# --- Test: comments and blank lines in config ---
echo "-- config parsing"
cat > "$HOME/.grisbirc" <<EOF

# this is a comment
path ~/testdata
   # indented comment

EOF
outdir3="$TMPDIR_TEST/output3"
mkdir -p "$outdir3"
cd "$outdir3"
output=$(printf 'secret\nsecret\n' | "$GRISBI" 2>&1)
if echo "$output" | grep -q "1 archive(s) created"; then
  ok "config with comments and blank lines"
else
  die "config parsing failed: $output"
fi

# --- Test: --prune missing argument ---
echo "-- prune: missing argument"
if output=$("$GRISBI" --prune 2>&1); then
  die "prune without days should exit non-zero"
else
  if echo "$output" | grep -q "Usage.*prune"; then
    ok "prune missing arg shows usage"
  else
    die "unexpected error: $output"
  fi
fi

# --- Test: --prune non-numeric argument ---
echo "-- prune: non-numeric argument"
if output=$("$GRISBI" --prune abc 2>&1); then
  die "prune with non-numeric arg should exit non-zero"
else
  if echo "$output" | grep -q "Usage.*prune"; then
    ok "prune non-numeric shows usage"
  else
    die "unexpected error: $output"
  fi
fi

# --- Test: --prune zero days ---
echo "-- prune: zero days"
if output=$("$GRISBI" --prune 0 2>&1); then
  die "prune with 0 days should exit non-zero"
else
  if echo "$output" | grep -q "Usage.*prune"; then
    ok "prune zero days shows usage"
  else
    die "unexpected error: $output"
  fi
fi

# --- Test: --prune deletes old files, keeps recent ---
echo "-- prune: deletes old, keeps recent"
prunedir="$TMPDIR_TEST/prunedir"
mkdir -p "$prunedir"
# Create fake .age files with old and recent timestamps
touch "$prunedir/docs-2020-01-15-120000.tar.gz.age"   # old
touch "$prunedir/docs-2020-06-01-080000.tar.gz.age"   # old
# Use a date far in the future to ensure it's "recent"
touch "$prunedir/docs-2099-12-31-235959.tar.gz.age"   # recent (far future)
touch "$prunedir/notes-2020-03-10-090000.tar.gz.age"   # old
touch "$prunedir/unrelated.txt"                         # not a .age file
cd "$prunedir"
output=$("$GRISBI" --prune 30 2>&1)
if echo "$output" | grep -q "3 archive(s) deleted"; then
  ok "prune deleted 3 old archives"
else
  die "expected 3 deletions: $output"
fi
# The future-dated file should still exist
if [[ -f "$prunedir/docs-2099-12-31-235959.tar.gz.age" ]]; then
  ok "prune kept recent archive"
else
  die "prune should not have deleted recent archive"
fi
# unrelated.txt should still exist
if [[ -f "$prunedir/unrelated.txt" ]]; then
  ok "prune ignores non-.age files"
else
  die "prune should not delete non-.age files"
fi

# --- Test: --prune in empty directory ---
echo "-- prune: empty directory"
emptydir="$TMPDIR_TEST/emptydir"
mkdir -p "$emptydir"
cd "$emptydir"
output=$("$GRISBI" --prune 7 2>&1)
if echo "$output" | grep -q "0 archive(s) deleted"; then
  ok "prune in empty dir deletes nothing"
else
  die "unexpected output: $output"
fi

# --- Test: --prune with file that has no parseable timestamp ---
echo "-- prune: unparseable timestamp"
baddir="$TMPDIR_TEST/baddir"
mkdir -p "$baddir"
touch "$baddir/docs-notadate.tar.gz.age"
touch "$baddir/docs-2020-01-15-120000.tar.gz.age"  # old, should be deleted
cd "$baddir"
output=$("$GRISBI" --prune 30 2>&1)
if echo "$output" | grep -q "1 archive(s) deleted"; then
  ok "prune skips unparseable, deletes valid old"
else
  die "unexpected output: $output"
fi
if [[ -f "$baddir/docs-notadate.tar.gz.age" ]]; then
  ok "unparseable file kept"
else
  die "unparseable file should not be deleted"
fi

# --- Test: restore missing argument ---
echo "-- restore missing argument"
if output=$("$GRISBI" --restore 2>&1); then
  die "should exit non-zero without file argument"
else
  if echo "$output" | grep -q "Usage"; then
    ok "restore usage error"
  else
    die "unexpected error: $output"
  fi
fi

# --- Test: restore nonexistent file ---
echo "-- restore nonexistent file"
if output=$("$GRISBI" --restore /nonexistent.tar.gz.age 2>&1); then
  die "should exit non-zero for nonexistent file"
else
  if echo "$output" | grep -q "not found"; then
    ok "restore file not found error"
  else
    die "unexpected error: $output"
  fi
fi

# --- Test: restore round-trip ---
echo "-- restore round-trip"
restore_dir="$TMPDIR_TEST/restored"
mkdir -p "$restore_dir"
cd "$restore_dir"
output=$(printf 'secret\n' | "$GRISBI" --restore "$age_file" 2>&1)
if echo "$output" | grep -q "Restored from"; then
  ok "restore success message"
else
  die "unexpected restore output: $output"
fi
if [[ -f "$restore_dir/testdata/file.txt" ]]; then
  content=$(cat "$restore_dir/testdata/file.txt")
  if [[ "$content" == "hello" ]]; then
    ok "restored file content matches"
  else
    die "restored content mismatch: $content"
  fi
else
  die "restored file not found at $restore_dir/testdata/file.txt"
fi

# --- Summary ---
echo
total=$((pass + fail))
echo "$pass/$total tests passed"
if [[ $fail -gt 0 ]]; then
  exit 1
fi
