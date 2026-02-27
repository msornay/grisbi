# grisbi

Encrypted backups of personal text files using [age](https://age-encryption.org/) + `tar`. Archives are created in the current working directory.

## Prerequisites

- [age](https://github.com/FiloSottile/age): `brew install age`
- (optional) [age-plugin-batchpass](https://github.com/FiloSottile/age): for non-interactive passphrase input in tests

## Configuration

Create `~/.grisbirc`:

```
# paths to back up (one per line, ~ expanded)
~/Documents/personal
~/notes/private
~/.ssh

# back up each subdirectory of ~/projects as a separate archive
folder ~/projects
```

Directives:
- `path <dir>` — back up this directory as a single archive (supports `~` expansion)
- `directory <dir>` — alias for `path`
- `folder <dir>` — back up each immediate subdirectory of `<dir>` as a separate archive (note: does **not** back up the directory itself — use `path` for that)
- `<dir>` — bare path (no directive), treated as `path <dir>`
- Lines starting with `#` or blank lines are ignored
- Paths support `~`, `$HOME`, and `$VAR` expansion

## Usage

### Backup

```bash
grisbi
```

Prompts for a passphrase (with confirmation), then creates one `<name>-YYYY-MM-DD-HHMMSS.tar.gz.age` archive per configured path in the current directory.

### Restore

```bash
grisbi --restore <file.tar.gz.age>
```

Prompts for passphrase, decrypts and extracts into the current directory.

### Validate config

```bash
grisbi --check
```

Shows which directories would be backed up without creating archives. Useful for verifying `.grisbirc` is configured correctly.

### Prune old backups

```bash
grisbi --prune <days>
```

Deletes `.tar.gz.age` files in the current directory older than the given number of days (based on the timestamp in the filename).

## Install

```bash
ln -s "$(pwd)/grisbi.py" ~/bin/grisbi
```

## Scheduled backups on macOS

You can run grisbi automatically every day using a macOS LaunchAgent.

### 1. Store the passphrase in Keychain

```bash
security add-generic-password -s grisbi -a "$USER" -w
```

This prompts for the passphrase and stores it securely. To verify:

```bash
security find-generic-password -s grisbi -a "$USER" -w
```

### 2. Create a wrapper script

Save this as `~/bin/grisbi-daily` (or wherever you keep scripts):

```bash
#!/bin/bash
set -euo pipefail

BACKUP_DIR="$HOME/Backups/grisbi"
PRUNE_DAYS=90

mkdir -p "$BACKUP_DIR"
cd "$BACKUP_DIR"

export AGE_PASSPHRASE
AGE_PASSPHRASE=$(security find-generic-password -s grisbi -a "$USER" -w)

grisbi
grisbi --prune "$PRUNE_DAYS"
```

```bash
chmod +x ~/bin/grisbi-daily
```

### 3. Install the LaunchAgent

Save this as `~/Library/LaunchAgents/com.grisbi.daily.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.grisbi.daily</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-l</string>
        <string>-c</string>
        <string>~/bin/grisbi-daily</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>12</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/grisbi-daily.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/grisbi-daily.log</string>
</dict>
</plist>
```

Load it:

```bash
launchctl load ~/Library/LaunchAgents/com.grisbi.daily.plist
```

This runs grisbi daily at noon. Missed runs (laptop was asleep) execute at the next wake. To unload:

```bash
launchctl unload ~/Library/LaunchAgents/com.grisbi.daily.plist
```

**Note:** Requires `age` and `age-plugin-batchpass` in your PATH (the login shell `-l` flag ensures `brew` paths are available).

### Periodic backups (every N hours)

To run backups at a fixed interval instead of a specific time, use `StartInterval` (in seconds). This example backs up every 4 hours.

The wrapper script and Keychain setup are the same as above. Only the plist changes.

Save this as `~/Library/LaunchAgents/com.grisbi.periodic.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.grisbi.periodic</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-l</string>
        <string>-c</string>
        <string>~/bin/grisbi-daily</string>
    </array>
    <key>StartInterval</key>
    <integer>14400</integer>
    <key>StandardOutPath</key>
    <string>/tmp/grisbi-periodic.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/grisbi-periodic.log</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.grisbi.periodic.plist
```

Unlike `StartCalendarInterval`, `StartInterval` does **not** catch up on missed runs — if the laptop was asleep for 8 hours, it runs once on wake, not twice. Adjust the interval (in seconds) to suit: 3600 = 1 hour, 14400 = 4 hours, 21600 = 6 hours.

## Testing

```bash
make test
```

Requires `age` and `age-plugin-batchpass`. Tests are skipped if either is missing.
