"""Thumbnail and preview generation for documents."""

from __future__ import annotations

import io
import uuid
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

from lesspaper_ngl.core.exceptions import ValidationError
from lesspaper_ngl.storage.service import StorageService

_DEFAULT_THUMB_SIZE = (240, 320)
_DEFAULT_PREVIEW_MAX_WIDTH = 1400
_JPEG_QUALITY = 85


@dataclass(frozen=True)
class PreviewResult:
    thumbnail_bytes: bytes
    preview_bytes: bytes | None
    thumbnail_key: str
    preview_key: str | None


def generate_thumbnail_bytes(
    source_path: Path,
    mime_type: str,
    *,
    max_size: tuple[int, int] = _DEFAULT_THUMB_SIZE,
) -> bytes:
    """Render a JPEG thumbnail from the first page or image."""
    image = _render_first_page_image(source_path, mime_type, max_width=max_size[0] * 2)
    image = ImageOps.exif_transpose(image)
    image.thumbnail(max_size, Image.Resampling.LANCZOS)
    return _to_jpeg(image)


def generate_preview_bytes(
    source_path: Path,
    mime_type: str,
    *,
    max_width: int = _DEFAULT_PREVIEW_MAX_WIDTH,
) -> bytes | None:
    """Render a larger JPEG preview when supported."""
    mime = mime_type.lower()
    if mime not in {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "text/plain",
        "text/markdown",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }:
        return None
    image = _render_first_page_image(source_path, mime_type, max_width=max_width)
    image = ImageOps.exif_transpose(image)
    if image.width > max_width:
        ratio = max_width / image.width
        new_size = (max_width, max(1, int(image.height * ratio)))
        image = image.resize(new_size, Image.Resampling.LANCZOS)
    return _to_jpeg(image)


def generate_previews(
    source_path: Path,
    mime_type: str,
    document_id: uuid.UUID,
    *,
    include_preview: bool = True,
) -> PreviewResult:
    """Generate thumbnail and optional preview JPEG bytes with storage keys."""
    thumb = generate_thumbnail_bytes(source_path, mime_type)
    preview = generate_preview_bytes(source_path, mime_type) if include_preview else None
    base = f"{document_id}"
    return PreviewResult(
        thumbnail_bytes=thumb,
        preview_bytes=preview,
        thumbnail_key=f"{base}/thumb.jpg",
        preview_key=f"{base}/preview.jpg" if preview else None,
    )


async def persist_previews(
    storage: StorageService,
    document_id: uuid.UUID,
    source_path: Path,
    mime_type: str,
    *,
    include_preview: bool = True,
) -> PreviewResult:
    """Generate previews and write them through storage."""
    result = generate_previews(
        source_path,
        mime_type,
        document_id,
        include_preview=include_preview,
    )
    await storage.write_derived("thumbnail", result.thumbnail_key, result.thumbnail_bytes)
    if result.preview_bytes and result.preview_key:
        await storage.write_derived("preview", result.preview_key, result.preview_bytes)
    return result


def _render_first_page_image(
    source_path: Path,
    mime_type: str,
    *,
    max_width: int,
) -> Image.Image:
    mime = mime_type.lower()
    if mime == "application/pdf":
        return _pdf_first_page_image(source_path, max_width=max_width)
    if mime in {"image/png", "image/jpeg"}:
        with Image.open(source_path) as img:
            return img.convert("RGB")
    if mime in {
        "text/plain",
        "text/markdown",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }:
        return _text_placeholder_image(source_path, max_width=max_width)
    raise ValidationError(f"Preview not supported for MIME type: {mime_type}")


def _text_placeholder_image(path: Path, *, max_width: int) -> Image.Image:
    """Create a simple first-page preview for text-like documents."""
    from PIL import ImageDraw, ImageFont

    width = max(320, min(max_width, 800))
    height = int(width * 1.3)
    image = Image.new("RGB", (width, height), color=(248, 250, 252))
    draw = ImageDraw.Draw(image)
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        raw = path.name
    lines = raw.splitlines()[:40] or [path.name]
    font = ImageFont.load_default()
    y = 16
    margin = 16
    for line in lines:
        draw.text((margin, y), line[:120], fill=(30, 41, 59), font=font)
        y += 14
        if y > height - 20:
            break
    return image


def _pdf_first_page_image(path: Path, *, max_width: int) -> Image.Image:
    with pymupdf.open(path) as doc:
        if doc.page_count == 0:
            raise ValidationError("PDF has no pages")
        page = doc.load_page(0)
        zoom = max(1.0, max_width / max(page.rect.width, 1.0))
        matrix = pymupdf.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def _to_jpeg(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    rgb = image.convert("RGB")
    rgb.save(buffer, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
    return buffer.getvalue()
