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
- `path <dir>` — directory to back up (supports `~` expansion)
- `folder <dir>` — back up each immediate subdirectory of `<dir>` as a separate archive
- `<dir>` — bare path (no directive), treated as `path <dir>`
- Lines starting with `#` or blank lines are ignored

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

### Prune old backups

```bash
grisbi --prune <days>
```

Deletes `.tar.gz.age` files in the current directory older than the given number of days (based on the timestamp in the filename).

## Install

```bash
ln -s "$(pwd)/grisbi.py" ~/bin/grisbi
```

## Testing

```bash
make test
```

Requires `age` and `age-plugin-batchpass`. Tests are skipped if either is missing.
