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

# back up each subdirectory of ~/projects as a separate archive
folder ~/projects
```

Directives:
- `path <dir>` — directory to back up (supports `~` expansion)
- `folder <dir>` — back up each immediate subdirectory of `<dir>` as a separate archive
- Lines starting with `#` or blank lines are ignored

## Script: `grisbi.py`

- [x] Write `grisbi.sh` (~40 lines of bash)
- [x] Rewrite in Python (`grisbi.py`)
- [x] Add `folder` directive for backing up subdirectories individually

### Config parser

- Read `~/.grisbirc` line by line
- Skip comments (`#`) and blank lines
- Parse `path` and `folder` directives
- Expand `~` to `$HOME`
- Error if no paths configured

### Passphrase prompt

- Prompt for passphrase (uses `getpass` on TTY, reads stdin when piped)
- Prompt again for confirmation
- Abort if they don't match
- Export `AGE_PASSPHRASE` env var (supported since age v1.1+)

### Backup loop

For each configured path:
1. `tar cz -C <parent> <basename>` — tar relative to parent dir
2. Pipe to `age -e -p -o ./<basename>-YYYY-MM-DD-HHMMSS.tar.gz.age` (writes to pwd)
3. Timestamp format: `%Y-%m-%d-%H%M%S`
4. Print each file as it's written

### Summary

- Print count of archives created and total size

## Install

- [ ] Symlink to PATH: `ln -s ~/src/repos/grisbi/grisbi.py ~/bin/grisbi` or add repo to PATH

## Testing

- [x] Run `grisbi` — encrypted `.age` files appear in pwd with correct timestamps
- [x] Verify round-trip: `age -d <file> | tar tz` lists expected contents

## Restore

- [x] `grisbi --restore <file>` subcommand

Usage: `grisbi --restore <file.tar.gz.age>` — prompts for passphrase, decrypts and extracts into pwd.

## Future

- [x] `grisbi --prune <days>` to delete backups older than N days
