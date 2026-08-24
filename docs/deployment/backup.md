# Backup and restore

lesspaper-ngl can create versioned `.folium` backup bundles (extension and `folium_version` manifest field are intentional persistence) and restore them from Settings or during first-run setup. Backup and restore do **not** require an AI or embedding provider.

## What a backup contains

A lesspaper-ngl backup is the canonical recoverable state of an installation:

- PostgreSQL dump (`pg_dump` custom format), excluding `application_logs` and `sessions`
- Original document blobs referenced by that dump
- User avatars (they cannot be rebuilt)
- Encrypted AI provider keys as they exist in the database (ciphertext only)
- A `manifest.json` and SHA-256 checksums

Intentionally excluded (rebuilt after restore where possible):

- Thumbnails and preview images
- Consume and export directory contents
- PaddleOCR model cache
- Application logs and live sessions

Embeddings and search indexes stay in the database dump so the Library is usable immediately. If you later change embedding providers, existing vectors are **not** treated as coverage for the new model.

The bundle never includes `.env` secrets, database passwords, or API keys in `manifest.json`. After restore, keep using the same `LESSPAPER_NGL_ENCRYPTION_KEY` if you need those stored provider credentials to decrypt.

## `/backups` mount

lesspaper-ngl only sees `/backups`. The host (or Docker) mounts local disk, NFS, or CIFS there. lesspaper-ngl does **not** mount network filesystems itself.

```text
# docker-compose.yml (api + worker)
${LESSPAPER_NGL_BACKUPS_HOST:-./data/backups}:/backups
```

Examples:

```text
/host/local/folium-backups:/backups
/mnt/nfs/folium-backups:/backups
/mnt/cifs/folium-backups:/backups
```

Default host path is `./data/backups` (installer: `$INSTALL_DIR/data/backups`). This is **not** the installer `INSTALL_DIR/backups/` directory used for config snapshots.

Existing deployments start without this bind until Compose is updated; `/backups` exists in the image but is not durable. Settings reports repository health. `/health/storage` is not failed solely because backups are unavailable.

## Using backups

Open **Settings → Backup & Restore** (administrators):

1. Optionally enable automatic backups (daily, weekly, or every N hours, UTC).
2. Set backups-to-keep (default 7) and verify-after-create (default on).
3. **Back up now** queues a worker job.
4. History supports Inspect, Verify, Restore, and Delete (restore/delete require confirmation).

Retention runs only after a successful backup that passed required verification. Failed or incomplete `.tmp` bundles are never counted. Corrupted backups are not auto-deleted if they would remove the only copy.

## First-run restore

A brand-new empty database no longer creates the bootstrap admin until you choose:

- **Set up new lesspaper-ngl**, or
- **Restore backup** from `.folium` files already in `/backups`

Browser upload is not available in V1. Copy the bundle onto the backup mount first.

After a successful restore, sign in with accounts from the backup (not the installer-generated password, unless that was the backup’s admin).

## Version compatibility

| Case | Behaviour |
|------|-----------|
| Same version | Supported |
| Older backup → newer app | Supported; Alembic upgrades after restore |
| Newer backup → older app | Rejected before destructive restore |
| Unknown format version | Rejected |

## Restore safety

Restore replaces PostgreSQL canonical state. lesspaper-ngl writes a best-effort safety dump under `/backups/.pre-restore-*` for authenticated restores (needs free disk). Originals are content-addressed and additive. If restore fails after the destructive database step, lesspaper-ngl attempts rollback from that dump when present. This is **not** a guarantee; keep off-host copies of `.folium` files.

During restore the worker idles. The Library becomes available after canonical restore; thumbnail rebuild continues in the background.

## V1 limitations

- Full backups only (no incremental / cloud / S3)
- No lesspaper-ngl-managed NFS/CIFS mounting
- No browser upload of backup files
- No backup-bundle encryption UI
- Host upgrades use `lesspaper-ngl update` (or the `folium` shim) / the installer; backups remain in-app (not part of the CLI update path)
