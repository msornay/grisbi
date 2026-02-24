# grisbi — encrypted backup tool

Encrypted backups of personal text files using `age` + `tar`. Archives are created in the current working directory.

## Prerequisites

- [ ] Install `age`: `brew install age`

## Config: `~/.grisbirc`

- [ ] Create `~/.grisbirc` with the following format:

```
# paths to back up (one per line, ~ expanded)
path ~/Documents/personal
path ~/notes/private
path ~/.ssh
```

Directives:
- `path <dir>` — directory to back up (supports `~` expansion)
- Lines starting with `#` or blank lines are ignored

## Script: `grisbi.sh`

- [x] Write `grisbi.sh` (~40 lines of bash)

### Config parser

- Read `~/.grisbirc` line by line
- Skip comments (`#`) and blank lines
- Parse `path` directives into an array
- Expand `~` to `$HOME`
- Error if no paths configured

### Passphrase prompt

- Prompt once with `read -s -p "Passphrase: " PASSPHRASE`
- Prompt again for confirmation: `read -s -p "Confirm: " PASSPHRASE2`
- Abort if they don't match
- Export `AGE_PASSPHRASE` env var (supported since age v1.1+)

### Backup loop

For each configured path:
1. `tar cz -C <parent> <basename>` — tar relative to parent dir
2. Pipe to `age -e -p -o ./<basename>-YYYY-MM-DD-HHMMSS.tar.gz.age` (writes to pwd)
3. Timestamp format: `date +%Y-%m-%d-%H%M%S`
4. Print each file as it's written

### Summary

- Print count of archives created and total size

## Install

- [ ] Symlink to PATH: `ln -s ~/src/repos/grisbi/grisbi.sh ~/bin/grisbi` or add repo to PATH

## Testing

- [x] Run `grisbi` — encrypted `.age` files appear in pwd with correct timestamps
- [x] Verify round-trip: `age -d <file> | tar tz` lists expected contents

## Restore

- [x] `grisbi --restore <file>` subcommand

Usage: `grisbi --restore <file.tar.gz.age>` — prompts for passphrase, decrypts and extracts into pwd.

## Future

- [x] `grisbi --prune <days>` to delete backups older than N days
