#!/usr/bin/env bash
# Backs up the production database to ~/backups (deploy/README.md, "Backups and restore").
#
#   bash deploy/backup.sh      # one backup now; deploy/systemd/ runs it every day
#
# The dump is written under a temporary name, checked with pg_restore --list, and only then renamed to
# fitscan-<UTC date>_<time>.dump, so a failed or cut-off dump never looks like a good one. Dumps older
# than BACKUP_KEEP_DAYS (default 14) are deleted. The folder is outside the repository and readable only
# by its owner. Nothing in the database is changed, and no value from .env is printed.
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
backup_dir=${BACKUP_DIR:-$HOME/backups}
keep_days=${BACKUP_KEEP_DAYS:-14}

case "$backup_dir/" in
  "$repo"/*) echo "BACKUP_DIR must be outside the repository ($repo)" >&2; exit 1 ;;
esac

cd "$repo"
compose=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)
if ! docker info >/dev/null 2>&1; then
  compose=(sudo -n "${compose[@]}") # the user is not in the docker group (deploy/README.md, step 3)
fi

umask 077
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"

name="fitscan-$(date -u +%Y-%m-%d_%H%M%S).dump"
partial="$backup_dir/.$name.partial"
trap 'status=$?; rm -f "$partial"; if [ "$status" -ne 0 ]; then echo "Backup FAILED (exit $status); no dump was kept" >&2; fi' EXIT

"${compose[@]}" exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' > "$partial" < /dev/null
"${compose[@]}" exec -T db pg_restore --list < "$partial" > /dev/null # fails if the dump is unreadable
mv "$partial" "$backup_dir/$name"

find "$backup_dir" -maxdepth 1 -type f -name 'fitscan-*.dump' -mtime +"$keep_days" -delete
kept=$(find "$backup_dir" -maxdepth 1 -type f -name 'fitscan-*.dump' | wc -l)
echo "Backup written: $backup_dir/$name ($(du -h "$backup_dir/$name" | cut -f1)); $kept dump(s) kept"
