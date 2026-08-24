"""Document management integration tests."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from lesspaper_ngl.storage.service import StorageService


@pytest.mark.asyncio
async def test_upload_txt_document(
    auth_client: AsyncClient,
    sample_txt_path,
    run_extraction,
) -> None:
    with sample_txt_path.open("rb") as fh:
        response = await auth_client.post(
            "/api/documents/upload",
            files={"file": ("sample.txt", fh, "text/plain")},
        )
    assert response.status_code == 201
    doc = response.json()
    assert doc["original_filename"] == "sample.txt"
    assert doc["mime_type"] == "text/plain"
    assert doc["inbox"] is True

    await run_extraction(uuid.UUID(doc["id"]))

    content = await auth_client.get(f"/api/documents/{doc['id']}/content")
    assert content.status_code == 200
    pages = content.json()["pages"]
    assert pages
    assert "LPPSA" in pages[0]["text"]
    assert "420,000" in pages[0]["text"] or "420000" in pages[0]["text"]


@pytest.mark.asyncio
async def test_upload_pdf_document(
    auth_client: AsyncClient,
    sample_pdf_path,
    run_extraction,
) -> None:
    with sample_pdf_path.open("rb") as fh:
        response = await auth_client.post(
            "/api/documents/upload",
            files={"file": ("lppsa-refinance.pdf", fh, "application/pdf")},
        )
    assert response.status_code == 201
    doc = response.json()
    assert doc["mime_type"] == "application/pdf"

    await run_extraction(uuid.UUID(doc["id"]))

    content = await auth_client.get(f"/api/documents/{doc['id']}/content")
    assert content.status_code == 200
    assert "LPPSA" in content.json()["pages"][0]["text"]


@pytest.mark.asyncio
async def test_duplicate_upload_returns_409(
    auth_client: AsyncClient,
    sample_txt_path,
) -> None:
    with sample_txt_path.open("rb") as fh:
        first = await auth_client.post(
            "/api/documents/upload",
            files={"file": ("sample.txt", fh, "text/plain")},
        )
    assert first.status_code == 201
    first_id = first.json()["id"]

    with sample_txt_path.open("rb") as fh:
        second = await auth_client.post(
            "/api/documents/upload",
            files={"file": ("sample-copy.txt", fh, "text/plain")},
        )
    assert second.status_code == 409
    body = second.json()
    assert body["duplicate"] is True
    assert body["existing_document_id"] == first_id


@pytest.mark.asyncio
async def test_duplicate_upload_skip(
    auth_client: AsyncClient,
    sample_txt_path,
) -> None:
    with sample_txt_path.open("rb") as fh:
        first = await auth_client.post(
            "/api/documents/upload",
            files={"file": ("sample.txt", fh, "text/plain")},
        )
    assert first.status_code == 201
    first_id = first.json()["id"]

    with sample_txt_path.open("rb") as fh:
        second = await auth_client.post(
            "/api/documents/upload",
            data={"on_duplicate": "skip"},
            files={"file": ("sample-copy.txt", fh, "text/plain")},
        )
    assert second.status_code == 200
    body = second.json()
    assert body["status"] == "duplicate"
    assert body["existing_document_id"] == first_id


@pytest.mark.asyncio
async def test_reupload_after_trash_reingests(
    auth_client: AsyncClient,
    sample_txt_path,
) -> None:
    with sample_txt_path.open("rb") as fh:
        first = await auth_client.post(
            "/api/documents/upload",
            files={"file": ("sample.txt", fh, "text/plain")},
        )
    assert first.status_code == 201
    first_id = first.json()["id"]

    trash = await auth_client.post(f"/api/documents/{first_id}/trash")
    assert trash.status_code == 200
    assert trash.json()["is_trashed"] is True

    with sample_txt_path.open("rb") as fh:
        second = await auth_client.post(
            "/api/documents/upload",
            files={"file": ("sample.txt", fh, "text/plain")},
        )
    assert second.status_code == 201, second.text
    second_id = second.json()["id"]
    assert second_id != first_id

    old = await auth_client.get(f"/api/documents/{first_id}")
    assert old.status_code == 404

    new = await auth_client.get(f"/api/documents/{second_id}")
    assert new.status_code == 200
    assert new.json()["is_trashed"] is False


@pytest.mark.asyncio
async def test_reupload_after_trash_with_skip_reingests(
    auth_client: AsyncClient,
    sample_txt_path,
) -> None:
    with sample_txt_path.open("rb") as fh:
        first = await auth_client.post(
            "/api/documents/upload",
            files={"file": ("sample.txt", fh, "text/plain")},
        )
    assert first.status_code == 201
    first_id = first.json()["id"]

    trash = await auth_client.post(f"/api/documents/{first_id}/trash")
    assert trash.status_code == 200

    with sample_txt_path.open("rb") as fh:
        second = await auth_client.post(
            "/api/documents/upload",
            data={"on_duplicate": "skip"},
            files={"file": ("sample-copy.txt", fh, "text/plain")},
        )
    assert second.status_code == 201, second.text
    body = second.json()
    assert body.get("status") != "duplicate"
    second_id = body["id"]
    assert second_id != first_id

    old = await auth_client.get(f"/api/documents/{first_id}")
    assert old.status_code == 404


@pytest.mark.asyncio
async def test_upload_relative_path_enters_inbox_with_pending_path(
    auth_client: AsyncClient,
    sample_txt_path,
) -> None:
    """Folder/tree upload without folder_id stays in Inbox for review."""
    with sample_txt_path.open("rb") as fh:
        response = await auth_client.post(
            "/api/documents/upload",
            data={"relative_path": "ImportRoot/Nested/notes.txt", "on_duplicate": "skip"},
            files={"file": ("notes.txt", fh, "text/plain")},
        )
    assert response.status_code == 201, response.text
    doc = response.json()
    assert doc["original_filename"] == "notes.txt"
    assert doc["inbox"] is True
    assert doc["pending_folder_path"] == "ImportRoot/Nested"

    folders = await auth_client.get("/api/folders")
    assert folders.status_code == 200
    names = {f["name"] for f in folders.json()}
    assert "ImportRoot" not in names
    assert "Nested" not in names


@pytest.mark.asyncio
async def test_upload_relative_path_under_folder_creates_tree(
    auth_client: AsyncClient,
    sample_txt_path,
) -> None:
    """Tree upload into an explicit library folder materializes immediately."""
    parent = await auth_client.post("/api/folders", json={"name": "LibraryParent"})
    assert parent.status_code == 201, parent.text
    parent_id = parent.json()["id"]

    with sample_txt_path.open("rb") as fh:
        response = await auth_client.post(
            "/api/documents/upload",
            data={
                "relative_path": "ImportRoot/Nested/notes.txt",
                "folder_id": parent_id,
                "on_duplicate": "skip",
            },
            files={"file": ("notes.txt", fh, "text/plain")},
        )
    assert response.status_code == 201, response.text
    doc = response.json()
    assert doc["inbox"] is False
    assert "ImportRoot" in (doc["folder_path"] or "")
    assert "Nested" in (doc["folder_path"] or "")

    folders = await auth_client.get("/api/folders")
    assert folders.status_code == 200
    names = {f["name"] for f in folders.json()}
    assert "ImportRoot" in names
    assert "Nested" in names


@pytest.mark.asyncio
async def test_update_metadata(auth_client: AsyncClient, uploaded_txt_doc: dict) -> None:
    doc_id = uploaded_txt_doc["id"]
    response = await auth_client.patch(
        f"/api/documents/{doc_id}/metadata",
        json={"title": "LPPSA Refinance Pack", "notes": "Review before submission"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "LPPSA Refinance Pack"
    assert body["notes"] == "Review before submission"


@pytest.mark.asyncio
async def test_trash_restore_and_permanent_delete(
    auth_client: AsyncClient,
    uploaded_txt_doc: dict,
) -> None:
    doc_id = uploaded_txt_doc["id"]

    trash = await auth_client.post(f"/api/documents/{doc_id}/trash")
    assert trash.status_code == 200
    assert trash.json()["is_trashed"] is True

    listed = await auth_client.get("/api/documents", params={"trashed": True})
    assert any(item["id"] == doc_id for item in listed.json()["items"])

    restore = await auth_client.post(f"/api/documents/{doc_id}/restore")
    assert restore.status_code == 200
    assert restore.json()["is_trashed"] is False

    await auth_client.post(f"/api/documents/{doc_id}/trash")
    delete = await auth_client.delete(f"/api/documents/{doc_id}")
    assert delete.status_code == 200

    get_resp = await auth_client.get(f"/api/documents/{doc_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_download_document(
    auth_client: AsyncClient,
    uploaded_txt_doc: dict,
    sample_txt_bytes: bytes,
) -> None:
    doc_id = uploaded_txt_doc["id"]
    response = await auth_client.get(f"/api/documents/{doc_id}/download")
    assert response.status_code == 200
    assert response.content == sample_txt_bytes


@pytest.mark.asyncio
async def test_storage_path_traversal_rejected() -> None:
    storage = StorageService()
    with pytest.raises(Exception) as exc_info:
        storage.open_original_path("../../etc/passwd")
    assert exc_info.value.__class__.__name__ in {"ValidationError", "NotFoundError"}

    with pytest.raises(Exception):
        storage.originals_absolute("../outside.txt")
