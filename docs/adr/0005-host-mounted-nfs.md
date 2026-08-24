# ADR-0005: Host-mounted NFS

## Status
Accepted

## Context
Document blobs may live on a NAS.

## Decision
lesspaper-ngl **never** mounts NFS. The Docker **host** mounts NFS (or local dirs) and bind-mounts into containers. PostgreSQL data stays on a **local** named volume.

## Rationale
Compose volumes and `StorageService` health probes assume POSIX paths. NFS stale-handle behaviour is handled as storage unavailable, not as an in-app mount retry.

## Consequences
Operators must configure `/etc/fstab` (or equivalent) themselves. Default `./data/*` binds are local directories for development.

## Alternatives considered
FUSE/NFS client inside the container (not implemented).
