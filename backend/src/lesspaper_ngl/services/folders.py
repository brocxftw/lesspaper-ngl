"""Folder hierarchy services."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.core.exceptions import ConflictError, NotFoundError, ValidationError
from lesspaper_ngl.models import Document, Folder, FolderKind

if TYPE_CHECKING:
    from lesspaper_ngl.storage.service import StorageService

SYSTEM_FOLDER_NAMES = {
    FolderKind.ROOT: "Documents",
    FolderKind.INBOX: "Inbox",
    FolderKind.TRASH: "Trash",
}


async def ensure_system_folders(session: AsyncSession, owner_id: uuid.UUID) -> dict[str, Folder]:
    result: dict[str, Folder] = {}
    for kind, name in SYSTEM_FOLDER_NAMES.items():
        folder = (
            await session.execute(
                select(Folder).where(
                    Folder.owner_id == owner_id,
                    Folder.kind == kind,
                )
            )
        ).scalar_one_or_none()
        if folder is None:
            parent_id = None
            path = name
            if kind != FolderKind.ROOT:
                root = result.get("root")
                if root is None:
                    root = (
                        await session.execute(
                            select(Folder).where(
                                Folder.owner_id == owner_id,
                                Folder.kind == FolderKind.ROOT,
                            )
                        )
                    ).scalar_one()
                    result["root"] = root
                parent_id = root.id
                path = f"{root.path_cache} / {name}" if root.path_cache else name
            folder = Folder(
                name=name,
                parent_id=parent_id,
                owner_id=owner_id,
                kind=kind,
                path_cache=path if kind != FolderKind.ROOT else name,
                sort_order=0
                if kind == FolderKind.ROOT
                else (1 if kind == FolderKind.INBOX else 999),
            )
            session.add(folder)
            await session.flush()
        key = kind.value
        result[key] = folder
    return result


async def get_folder(
    session: AsyncSession,
    folder_id: uuid.UUID,
    *,
    owner_id: uuid.UUID | None = None,
) -> Folder:
    folder = await session.get(Folder, folder_id)
    if folder is None or (owner_id is not None and folder.owner_id != owner_id):
        raise NotFoundError("Folder not found")
    return folder


async def get_inbox(session: AsyncSession, owner_id: uuid.UUID) -> Folder:
    folder = (
        await session.execute(
            select(Folder).where(
                Folder.owner_id == owner_id,
                Folder.kind == FolderKind.INBOX,
            )
        )
    ).scalar_one_or_none()
    if folder is None:
        folders = await ensure_system_folders(session, owner_id)
        return folders["inbox"]
    return folder


async def get_trash(session: AsyncSession, owner_id: uuid.UUID) -> Folder:
    folder = (
        await session.execute(
            select(Folder).where(
                Folder.owner_id == owner_id,
                Folder.kind == FolderKind.TRASH,
            )
        )
    ).scalar_one_or_none()
    if folder is None:
        folders = await ensure_system_folders(session, owner_id)
        return folders["trash"]
    return folder


async def get_root(session: AsyncSession, owner_id: uuid.UUID) -> Folder:
    folder = (
        await session.execute(
            select(Folder).where(
                Folder.owner_id == owner_id,
                Folder.kind == FolderKind.ROOT,
            )
        )
    ).scalar_one_or_none()
    if folder is None:
        folders = await ensure_system_folders(session, owner_id)
        return folders["root"]
    return folder


async def build_path_cache(session: AsyncSession, folder: Folder) -> str:
    parts: list[str] = [folder.name]
    current = folder
    seen: set[uuid.UUID] = {folder.id}
    while current.parent_id is not None:
        if current.parent_id in seen:
            raise ValidationError("Folder cycle detected")
        seen.add(current.parent_id)
        parent = await session.get(Folder, current.parent_id)
        if parent is None:
            break
        parts.append(parent.name)
        current = parent
    parts.reverse()
    return " / ".join(parts)


async def refresh_path_cache_subtree(session: AsyncSession, folder_id: uuid.UUID) -> None:
    """Recompute path_cache for folder and all descendants via recursive CTE."""
    await session.execute(
        text(
            """
            WITH RECURSIVE tree AS (
                SELECT id, name, parent_id, name::text AS path
                FROM folders
                WHERE id = :folder_id
                UNION ALL
                SELECT f.id, f.name, f.parent_id, (tree.path || ' / ' || f.name)::text
                FROM folders f
                JOIN tree ON f.parent_id = tree.id
            )
            UPDATE folders AS f
            SET path_cache = tree.path
            FROM tree
            WHERE f.id = tree.id
            """
        ),
        {"folder_id": folder_id},
    )


async def create_folder(
    session: AsyncSession,
    *,
    name: str,
    parent_id: uuid.UUID | None,
    owner_id: uuid.UUID,
) -> Folder:
    name = name.strip()
    if not name:
        raise ValidationError("Folder name is required")
    if parent_id is None:
        parent = await get_root(session, owner_id)
        parent_id = parent.id
    else:
        parent = await get_folder(session, parent_id, owner_id=owner_id)
        if parent.kind == FolderKind.TRASH:
            raise ValidationError("Cannot create folders inside Trash")

    existing = (
        await session.execute(
            select(Folder).where(
                Folder.parent_id == parent_id,
                Folder.owner_id == owner_id,
                Folder.name == name,
                Folder.is_trashed.is_(False),
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise ConflictError("A folder with this name already exists here")

    folder = Folder(
        name=name,
        parent_id=parent_id,
        owner_id=owner_id,
        kind=FolderKind.NORMAL,
        path_cache="",
    )
    session.add(folder)
    await session.flush()
    folder.path_cache = await build_path_cache(session, folder)
    await session.flush()
    await session.refresh(folder)
    return folder


async def find_child_folder(
    session: AsyncSession,
    parent_id: uuid.UUID,
    name: str,
    *,
    include_trashed: bool = False,
) -> Folder | None:
    stmt = select(Folder).where(
        Folder.parent_id == parent_id,
        Folder.name == name,
    )
    if not include_trashed:
        stmt = stmt.where(Folder.is_trashed.is_(False))
    return (await session.execute(stmt)).scalar_one_or_none()


async def ensure_child_folder(session: AsyncSession, *, parent_id: uuid.UUID, name: str) -> Folder:
    """Get or create a normal child folder under parent.

    Soft-deleted siblings with the same name are revived (folder row only) so
    pending filing paths can reuse them without hitting the sibling-name unique
    constraint.
    """
    parent = await get_folder(session, parent_id)
    existing = await find_child_folder(session, parent_id, name)
    if existing is not None:
        if existing.kind == FolderKind.TRASH:
            raise ValidationError("Cannot place documents under Trash")
        return existing

    # Unique constraint includes trashed rows — reuse instead of insert.
    trashed = await find_child_folder(session, parent_id, name, include_trashed=True)
    if trashed is not None and trashed.is_trashed:
        if trashed.kind == FolderKind.TRASH:
            raise ValidationError("Cannot place documents under Trash")
        if trashed.kind != FolderKind.NORMAL:
            raise ValidationError("Cannot reuse a system folder from Trash")
        trashed.is_trashed = False
        trashed.trashed_at = None
        await session.flush()
        return trashed

    try:
        return await create_folder(
            session,
            name=name,
            parent_id=parent_id,
            owner_id=parent.owner_id,
        )
    except ConflictError:
        # Concurrent create — fetch the winner
        again = await find_child_folder(session, parent_id, name)
        if again is None:
            raise
        return again


async def ensure_folder_path(
    session: AsyncSession,
    *,
    parent_id: uuid.UUID,
    segments: Sequence[str],
) -> Folder:
    """Ensure nested folders exist under parent; return the leaf folder."""
    parent = await get_folder(session, parent_id)
    if parent.kind == FolderKind.TRASH:
        raise ValidationError("Cannot create folders inside Trash")
    current = parent
    for segment in segments:
        current = await ensure_child_folder(session, parent_id=current.id, name=segment)
    return current


async def rename_folder(
    session: AsyncSession,
    folder_id: uuid.UUID,
    name: str,
    *,
    owner_id: uuid.UUID,
) -> Folder:
    folder = await get_folder(session, folder_id, owner_id=owner_id)
    if folder.kind != FolderKind.NORMAL:
        raise ValidationError("System folders cannot be renamed")
    name = name.strip()
    if not name:
        raise ValidationError("Folder name is required")
    existing = (
        await session.execute(
            select(Folder).where(
                Folder.parent_id == folder.parent_id,
                Folder.owner_id == owner_id,
                Folder.name == name,
                Folder.id != folder.id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise ConflictError("A folder with this name already exists here")
    folder.name = name
    await session.flush()
    await refresh_path_cache_subtree(session, folder.id)
    await session.refresh(folder)
    return folder


async def would_create_cycle(
    session: AsyncSession, folder_id: uuid.UUID, new_parent_id: uuid.UUID
) -> bool:
    if folder_id == new_parent_id:
        return True
    current_id: uuid.UUID | None = new_parent_id
    seen: set[uuid.UUID] = set()
    while current_id is not None:
        if current_id == folder_id:
            return True
        if current_id in seen:
            return True
        seen.add(current_id)
        parent = await session.get(Folder, current_id)
        if parent is None:
            break
        current_id = parent.parent_id
    return False


async def move_folder(
    session: AsyncSession,
    folder_id: uuid.UUID,
    new_parent_id: uuid.UUID,
    *,
    owner_id: uuid.UUID,
) -> Folder:
    folder = await get_folder(session, folder_id, owner_id=owner_id)
    if folder.kind != FolderKind.NORMAL:
        raise ValidationError("System folders cannot be moved")
    new_parent = await get_folder(session, new_parent_id, owner_id=owner_id)
    if new_parent.kind == FolderKind.TRASH:
        raise ValidationError("Cannot move folders into Trash")
    if await would_create_cycle(session, folder_id, new_parent_id):
        raise ValidationError("Cannot move a folder into its descendant")
    existing = (
        await session.execute(
            select(Folder).where(
                Folder.parent_id == new_parent_id,
                Folder.owner_id == owner_id,
                Folder.name == folder.name,
                Folder.id != folder.id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise ConflictError("A folder with this name already exists in the destination")
    folder.parent_id = new_parent_id
    await session.flush()
    await refresh_path_cache_subtree(session, folder.id)
    await session.refresh(folder)
    return folder


async def list_folder_tree(
    session: AsyncSession,
    owner_id: uuid.UUID,
    *,
    include_trashed: bool = False,
) -> Sequence[Folder]:
    await ensure_system_folders(session, owner_id)
    stmt = (
        select(Folder).where(Folder.owner_id == owner_id).order_by(Folder.sort_order, Folder.name)
    )
    if not include_trashed:
        stmt = stmt.where(Folder.is_trashed.is_(False))
    result = await session.execute(stmt)
    return result.scalars().all()


async def list_trashed_folders(session: AsyncSession, owner_id: uuid.UUID) -> Sequence[Folder]:
    await ensure_system_folders(session, owner_id)
    result = await session.execute(
        select(Folder)
        .where(
            Folder.owner_id == owner_id,
            Folder.is_trashed.is_(True),
            Folder.kind == FolderKind.NORMAL,
        )
        .order_by(Folder.trashed_at.desc().nullslast(), Folder.name)
    )
    return result.scalars().all()


async def trash_folder(
    session: AsyncSession, folder_id: uuid.UUID, *, owner_id: uuid.UUID
) -> Folder:
    """Soft-delete a folder and its subtree (folders + documents)."""
    folder = await get_folder(session, folder_id, owner_id=owner_id)
    if folder.kind != FolderKind.NORMAL:
        raise ValidationError("System folders cannot be deleted")
    if folder.is_trashed:
        return folder

    now = datetime.now(UTC)
    ids = await descendant_ids(session, folder.id, owner_id=owner_id)

    await session.execute(
        update(Folder)
        .where(
            Folder.owner_id == owner_id,
            Folder.id.in_(ids),
            Folder.kind == FolderKind.NORMAL,
        )
        .values(is_trashed=True, trashed_at=now)
    )
    await session.execute(
        update(Document)
        .where(
            Document.owner_id == owner_id,
            Document.folder_id.in_(ids),
            Document.is_trashed.is_(False),
        )
        .values(
            is_trashed=True,
            trashed_at=now,
            inbox=False,
            # Keep folder_id so trash preserves structure; remember origin.
            trashed_from_folder_id=Document.folder_id,
        )
    )
    await session.flush()
    folder = await get_folder(session, folder_id, owner_id=owner_id)
    await session.refresh(folder)
    return folder


async def restore_folder(
    session: AsyncSession, folder_id: uuid.UUID, *, owner_id: uuid.UUID
) -> Folder:
    """Restore a trashed folder and its documents."""
    folder = await get_folder(session, folder_id, owner_id=owner_id)
    if folder.kind != FolderKind.NORMAL:
        raise ValidationError("System folders cannot be restored this way")
    if not folder.is_trashed:
        return folder

    ids = await descendant_ids(session, folder.id, owner_id=owner_id)
    # Only restore folders that were trashed (avoid restoring unrelated)
    await session.execute(
        update(Folder)
        .where(
            Folder.owner_id == owner_id,
            Folder.id.in_(ids),
            Folder.is_trashed.is_(True),
        )
        .values(is_trashed=False, trashed_at=None)
    )
    await session.execute(
        update(Document)
        .where(
            Document.owner_id == owner_id,
            Document.folder_id.in_(ids),
            Document.is_trashed.is_(True),
        )
        .values(is_trashed=False, trashed_at=None, trashed_from_folder_id=None)
    )
    await session.flush()
    folder = await get_folder(session, folder_id, owner_id=owner_id)
    await session.refresh(folder)
    return folder


async def descendant_ids(
    session: AsyncSession,
    folder_id: uuid.UUID,
    *,
    owner_id: uuid.UUID | None = None,
) -> list[uuid.UUID]:
    if owner_id is None:
        query = text(
            """
            WITH RECURSIVE tree AS (
                SELECT id FROM folders WHERE id = :folder_id
                UNION ALL
                SELECT f.id FROM folders f JOIN tree ON f.parent_id = tree.id
            )
            SELECT id FROM tree
            """
        )
        params = {"folder_id": folder_id}
    else:
        query = text(
            """
            WITH RECURSIVE tree AS (
                SELECT id FROM folders
                WHERE id = :folder_id AND owner_id = :owner_id
                UNION ALL
                SELECT f.id FROM folders f JOIN tree ON f.parent_id = tree.id
                WHERE f.owner_id = :owner_id
            )
            SELECT id FROM tree
            """
        )
        params = {"folder_id": folder_id, "owner_id": owner_id}
    rows = await session.execute(
        query,
        params,
    )
    return [row[0] for row in rows.fetchall()]


async def delete_folder(
    session: AsyncSession,
    folder_id: uuid.UUID,
    *,
    owner_id: uuid.UUID,
    strategy: str,
    confirm_destructive: bool = False,
) -> None:
    folder = await get_folder(session, folder_id, owner_id=owner_id)
    if folder.kind != FolderKind.NORMAL:
        raise ValidationError("System folders cannot be deleted")

    if strategy == "trash":
        await trash_folder(session, folder_id, owner_id=owner_id)
        return

    child_folders = (
        (
            await session.execute(
                select(Folder).where(
                    Folder.owner_id == owner_id,
                    Folder.parent_id == folder.id,
                )
            )
        )
        .scalars()
        .all()
    )
    docs = (
        (
            await session.execute(
                select(Document).where(
                    Document.owner_id == owner_id,
                    Document.folder_id == folder.id,
                )
            )
        )
        .scalars()
        .all()
    )

    if not child_folders and not docs:
        await session.delete(folder)
        return

    if strategy == "move_to_parent":
        if folder.parent_id is None:
            raise ValidationError("Folder has no parent")
        parent_id = folder.parent_id
        await get_folder(session, parent_id, owner_id=owner_id)
        for child in child_folders:
            await move_folder(session, child.id, parent_id, owner_id=owner_id)
        if docs:
            await session.execute(
                update(Document)
                .where(
                    Document.owner_id == owner_id,
                    Document.folder_id == folder.id,
                )
                .values(folder_id=parent_id)
            )
        await session.delete(folder)
    elif strategy == "move_to_inbox":
        inbox = await get_inbox(session, owner_id)
        for child in list(child_folders):
            await move_folder(session, child.id, inbox.id, owner_id=owner_id)
        if docs:
            await session.execute(
                update(Document)
                .where(
                    Document.owner_id == owner_id,
                    Document.folder_id == folder.id,
                )
                .values(folder_id=inbox.id, inbox=True)
            )
        await session.delete(folder)
    elif strategy == "delete_documents":
        if not confirm_destructive:
            raise ValidationError("Destructive folder deletion requires confirm_destructive=true")
        trash = await get_trash(session, owner_id)
        # Trash this folder's documents and descendant documents
        ids = await descendant_ids(session, folder.id, owner_id=owner_id)
        await session.execute(
            update(Document)
            .where(
                Document.owner_id == owner_id,
                Document.folder_id.in_(ids),
            )
            .values(
                folder_id=trash.id,
                is_trashed=True,
                trashed_at=func.now(),
                inbox=False,
            )
        )
        # Delete descendant folders bottom-up
        await session.execute(
            text(
                """
                WITH RECURSIVE tree AS (
                    SELECT id, parent_id, 0 AS depth FROM folders
                    WHERE id = :folder_id AND owner_id = :owner_id
                    UNION ALL
                    SELECT f.id, f.parent_id, tree.depth + 1
                    FROM folders f JOIN tree ON f.parent_id = tree.id
                    WHERE f.owner_id = :owner_id
                )
                DELETE FROM folders WHERE id IN (
                    SELECT id FROM tree ORDER BY depth DESC
                )
                """
            ),
            {"folder_id": folder.id, "owner_id": owner_id},
        )
    else:
        raise ValidationError(f"Unknown deletion strategy: {strategy}")


async def folder_counts(
    session: AsyncSession, owner_id: uuid.UUID
) -> dict[uuid.UUID, tuple[int, int]]:
    """Return folder_id -> (children_count, document_count) for active items."""
    child_rows = await session.execute(
        select(Folder.parent_id, func.count())
        .where(
            Folder.owner_id == owner_id,
            Folder.parent_id.is_not(None),
            Folder.is_trashed.is_(False),
        )
        .group_by(Folder.parent_id)
    )
    doc_rows = await session.execute(
        select(Document.folder_id, func.count())
        .where(
            Document.owner_id == owner_id,
            Document.is_trashed.is_(False),
        )
        .group_by(Document.folder_id)
    )
    children = {row[0]: row[1] for row in child_rows.fetchall()}
    docs = {row[0]: row[1] for row in doc_rows.fetchall()}
    all_ids = set(children) | set(docs)
    folders = (
        (
            await session.execute(
                select(Folder.id).where(
                    Folder.owner_id == owner_id,
                    Folder.is_trashed.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    all_ids |= set(folders)
    return {fid: (children.get(fid, 0), docs.get(fid, 0)) for fid in all_ids}


async def permanently_delete_trashed_folder(
    session: AsyncSession, folder_id: uuid.UUID, *, owner_id: uuid.UUID
) -> None:
    folder = await get_folder(session, folder_id, owner_id=owner_id)
    if folder.kind != FolderKind.NORMAL:
        raise ValidationError("System folders cannot be permanently deleted")
    if not folder.is_trashed:
        raise ValidationError("Folder must be in Trash before permanent deletion")
    # Only delete if no documents remain in this folder (docs should be purged first)
    remaining = (
        await session.execute(
            select(func.count()).select_from(Document).where(Document.folder_id == folder.id)
        )
    ).scalar_one()
    if remaining:
        raise ValidationError("Folder still contains documents")
    children = (
        await session.execute(
            select(func.count()).select_from(Folder).where(Folder.parent_id == folder.id)
        )
    ).scalar_one()
    if children:
        raise ValidationError("Folder still contains subfolders")
    await session.delete(folder)
    await session.flush()


async def permanently_delete_trashed_subtree(
    session: AsyncSession,
    folder_id: uuid.UUID,
    *,
    owner_id: uuid.UUID,
    storage: StorageService | None = None,
) -> dict[str, int]:
    """Permanently delete a trashed folder, its subfolders, and their documents."""
    from lesspaper_ngl.services import documents as doc_service
    from lesspaper_ngl.storage.service import StorageService

    folder = await get_folder(session, folder_id, owner_id=owner_id)
    if folder.kind != FolderKind.NORMAL:
        raise ValidationError("System folders cannot be permanently deleted")
    if not folder.is_trashed:
        raise ValidationError("Folder must be in Trash before permanent deletion")

    storage_svc = storage or StorageService()
    ids = await descendant_ids(session, folder.id, owner_id=owner_id)
    doc_ids = (
        (
            await session.execute(
                select(Document.id).where(
                    Document.folder_id.in_(ids),
                    Document.owner_id == owner_id,
                    Document.is_trashed.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )

    deleted_docs = 0
    for doc_id in doc_ids:
        await doc_service.permanently_delete(
            session,
            doc_id,
            owner_id=owner_id,
            storage=storage_svc,
        )
        deleted_docs += 1

    # Delete folders deepest-first so parent RESTRICT FKs succeed.
    depth_rows = await session.execute(
        text(
            """
            WITH RECURSIVE tree AS (
                SELECT id, parent_id, 0 AS depth FROM folders
                WHERE id = :folder_id AND owner_id = :owner_id
                UNION ALL
                SELECT f.id, f.parent_id, tree.depth + 1
                FROM folders f JOIN tree ON f.parent_id = tree.id
                WHERE f.owner_id = :owner_id
            )
            SELECT id FROM tree ORDER BY depth DESC
            """
        ),
        {"folder_id": folder_id, "owner_id": owner_id},
    )
    deleted_folders = 0
    for (fid,) in depth_rows.fetchall():
        row = await session.get(Folder, fid)
        if row is None:
            continue
        if row.owner_id != owner_id or not row.is_trashed or row.kind != FolderKind.NORMAL:
            continue
        await session.delete(row)
        deleted_folders += 1
    await session.flush()
    return {"deleted_documents": deleted_docs, "deleted_folders": deleted_folders}
