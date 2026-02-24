#!/usr/bin/env bash
set -euo pipefail

CONFIG="$HOME/.grisbirc"

# --- Prune subcommand ---
if [[ "${1:-}" == "--prune" ]]; then
  if [[ $# -lt 2 ]] || ! [[ "$2" =~ ^[0-9]+$ ]] || [[ "$2" -eq 0 ]]; then
    echo "Usage: grisbi --prune <days>" >&2
    echo "Delete .tar.gz.age backups in the current directory older than <days> days." >&2
    exit 1
  fi
  max_age_days="$2"
  now=$(date +%s)
  cutoff=$((now - max_age_days * 86400))
  count=0
  freed=0

  for f in *.tar.gz.age; do
    [[ -f "$f" ]] || continue
    # Extract timestamp: expect <name>-YYYY-MM-DD-HHMMSS.tar.gz.age
    if [[ "$f" =~ -([0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{6})\.tar\.gz\.age$ ]]; then
      ts_str="${BASH_REMATCH[1]}"
      # Parse YYYY-MM-DD-HHMMSS → epoch
      file_epoch=$(date -d "${ts_str:0:10} ${ts_str:11:2}:${ts_str:13:2}:${ts_str:15:2}" +%s 2>/dev/null) \
        || file_epoch=$(date -j -f "%Y-%m-%d %H%M%S" "${ts_str:0:10} ${ts_str:11:6}" +%s 2>/dev/null) \
        || { echo "Warning: cannot parse timestamp in $f, skipping." >&2; continue; }
      if [[ "$file_epoch" -lt "$cutoff" ]]; then
        size=$(wc -c < "$f" | tr -d ' ')
        rm "$f"
        echo "Deleted $f ($size bytes)"
        count=$((count + 1))
        freed=$((freed + size))
      fi
    fi
  done

  echo "${count} archive(s) deleted, ${freed} bytes freed"
  exit 0
fi

# --- Backup (default) ---

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
