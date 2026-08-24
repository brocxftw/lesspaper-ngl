"""NDJSON protocol shared by the OCR subprocess runner and parent client."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

EventType = Literal["progress", "page", "done", "error"]


@dataclass(frozen=True, slots=True)
class OcrProgressEvent:
    done: int
    total: int


@dataclass(frozen=True, slots=True)
class OcrPageEvent:
    page_number: int
    text: str


@dataclass(frozen=True, slots=True)
class OcrDoneEvent:
    method: str
    page_count: int
    language: str | None


@dataclass(frozen=True, slots=True)
class OcrErrorEvent:
    message: str


OcrEvent = OcrProgressEvent | OcrPageEvent | OcrDoneEvent | OcrErrorEvent


def encode_event(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def parse_event_line(line: str) -> OcrEvent:
    raw = line.strip()
    if not raw:
        raise ValueError("empty OCR event line")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("OCR event must be a JSON object")
    kind = data.get("type")
    if kind == "progress":
        return OcrProgressEvent(done=int(data["done"]), total=int(data["total"]))
    if kind == "page":
        return OcrPageEvent(page_number=int(data["page_number"]), text=str(data.get("text") or ""))
    if kind == "done":
        lang = data.get("language")
        return OcrDoneEvent(
            method=str(data.get("method") or "paddleocr"),
            page_count=int(data.get("page_count") or 0),
            language=str(lang) if lang is not None else None,
        )
    if kind == "error":
        return OcrErrorEvent(message=str(data.get("message") or "OCR subprocess error"))
    raise ValueError(f"unknown OCR event type: {kind!r}")
