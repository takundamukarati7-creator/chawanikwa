#!/usr/bin/env bash
# Nightly encrypted PostgreSQL backup. Run as the 'foundit' user from cron.
# One-time setup:
#   sudo -u foundit mkdir -p /srv/foundit/backups && sudo chmod 700 /srv/foundit/backups
#   echo 'a-long-random-passphrase' | sudo -u foundit tee /srv/foundit/.backup_pass >/dev/null
#   sudo chmod 600 /srv/foundit/.backup_pass
set -euo pipefail
DEST=/srv/foundit/backups
KEEP_DAYS=30       # older backups are deleted, so purged records leave backups within 30 days
STAMP=$(date +%Y%m%d-%H%M%S)
set -a; source /etc/foundit.env; set +a
pg_dump "$DATABASE_URL" --format=custom \
  | gpg --batch --yes --symmetric --cipher-algo AES256 --passphrase-file /srv/foundit/.backup_pass \
  > "$DEST/foundit-$STAMP.dump.gpg"
find "$DEST" -name 'foundit-*.dump.gpg' -mtime +"$KEEP_DAYS" -delete
echo "Backup written: $DEST/foundit-$STAMP.dump.gpg"
