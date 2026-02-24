#!/usr/bin/env bash
set -euo pipefail

CONFIG="$HOME/.grisbirc"

# Parse config
if [[ ! -f "$CONFIG" ]]; then
  echo "Error: $CONFIG not found." >&2
  exit 1
fi

paths=()
while IFS= read -r line; do
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
  if [[ "$line" =~ ^path[[:space:]]+(.*) ]]; then
    dir="${BASH_REMATCH[1]}"
    dir="${dir/#\~/$HOME}"
    paths+=("$dir")
  fi
done < "$CONFIG"

if [[ ${#paths[@]} -eq 0 ]]; then
  echo "Error: no paths configured in $CONFIG." >&2
  exit 1
fi

# Passphrase prompt
read -s -p "Passphrase: " PASSPHRASE
echo
read -s -p "Confirm: " PASSPHRASE2
echo

if [[ "$PASSPHRASE" != "$PASSPHRASE2" ]]; then
  echo "Error: passphrases do not match." >&2
  exit 1
fi

export AGE_PASSPHRASE="$PASSPHRASE"

# Detect encryption method: prefer batchpass plugin, fall back to -p with temp file
if command -v age-plugin-batchpass >/dev/null 2>&1; then
  age_encrypt() { age -e -j batchpass -o "$1"; }
else
  age_encrypt() {
    local out="$1"
    local tmp
    tmp=$(mktemp)
    cat > "$tmp"
    age -e -p -o "$out" "$tmp" </dev/tty
    rm -f "$tmp"
  }
fi

# Backup loop
timestamp=$(date +%Y-%m-%d-%H%M%S)
count=0
total_size=0

for dir in "${paths[@]}"; do
  if [[ ! -d "$dir" ]]; then
    echo "Warning: $dir does not exist, skipping." >&2
    continue
  fi
  parent=$(dirname "$dir")
  base=$(basename "$dir")
  outfile="./${base}-${timestamp}.tar.gz.age"
  tar cz -C "$parent" "$base" | age_encrypt "$outfile"
  size=$(wc -c < "$outfile" | tr -d ' ')
  echo "$outfile ($size bytes)"
  count=$((count + 1))
  total_size=$((total_size + size))
done

echo "${count} archive(s) created, total size: ${total_size} bytes"
