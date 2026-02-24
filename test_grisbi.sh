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

# --- Summary ---
echo
total=$((pass + fail))
echo "$pass/$total tests passed"
if [[ $fail -gt 0 ]]; then
  exit 1
fi
