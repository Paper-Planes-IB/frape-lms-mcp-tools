"""Builder helpers for EditorJS content blocks.

Frappe LMS lessons store their content as an EditorJS JSON document in the
``content`` field.  This module provides small builder functions so the MCP
tools can compose lesson content programmatically without the caller needing
to know the exact EditorJS schema.

Each ``*_block`` function returns a single block dict.  :func:`build_content`
wraps a list of blocks into a valid EditorJS document.
"""

from __future__ import annotations

import random
import string
import time
from typing import Any

__all__ = [
    "paragraph_block",
    "header_block",
    "list_block",
    "image_block",
    "code_block",
    "embed_block",
    "quiz_block",
    "upload_block",
    "markdown_block",
    "build_content",
    "block_from_text",
]


def _random_id(length: int = 10) -> str:
    """Generate a random EditorJS-style block id."""
    return "".join(random.choices(string.ascii_letters, k=length))


def paragraph_block(text: str) -> dict[str, Any]:
    """A rich-text paragraph.  Inline HTML tags (<b>, <i>, <a>) are allowed."""
    return {
        "id": _random_id(),
        "type": "paragraph",
        "data": {"text": text},
    }


def header_block(text: str, level: int = 2) -> dict[str, Any]:
    """A heading.  ``level`` 1-6 (default 2 = h2)."""
    if level not in range(1, 7):
        raise ValueError(f"header level must be 1-6, got {level}")
    return {
        "id": _random_id(),
        "type": "header",
        "data": {"text": text, "level": level},
    }


def list_block(
    items: list[str],
    *,
    ordered: bool = False,
) -> dict[str, Any]:
    """A bulleted or numbered list.

    ``items`` is a flat list of strings.  For nested lists, pass dicts with
    ``{"content": "...", "items": [...]}`` instead of strings.
    """
    normalised = []
    for item in items:
        if isinstance(item, str):
            normalised.append({"content": item, "items": []})
        elif isinstance(item, dict):
            normalised.append(item)
        else:
            raise TypeError(f"list item must be str or dict, got {type(item)}")
    return {
        "id": _random_id(),
        "type": "list",
        "data": {
            "style": "ordered" if ordered else "unordered",
            "items": normalised,
        },
    }


def image_block(url: str, caption: str = "", *, with_border: bool = False,
                stretched: bool = False, with_background: bool = False) -> dict[str, Any]:
    """An image block.  ``url`` should be a file URL like ``/files/foo.png``."""
    return {
        "id": _random_id(),
        "type": "image",
        "data": {
            "file": {"url": url},
            "caption": caption,
            "withBorder": with_border,
            "stretched": stretched,
            "withBackground": with_background,
        },
    }


def code_block(code: str, language: str = "plaintext") -> dict[str, Any]:
    """A code block with syntax highlighting."""
    return {
        "id": _random_id(),
        "type": "codeBox",
        "data": {"code": code, "language": language},
    }


def embed_block(service: str, source: str, embed: str | None = None,
                caption: str = "") -> dict[str, Any]:
    """An embedded video or iframe.

    Common ``service`` values: ``youtube``, ``vimeo``, ``cloudflareStream``,
    ``bunnyStream``.  For YouTube, ``source`` is the full watch URL and
    ``embed`` is the video id (auto-extracted if omitted).
    """
    if embed is None and service == "youtube":
        embed = source.split("v=")[-1].split("&")[0] if "v=" in source else source.rstrip("/").split("/")[-1]
    elif embed is None:
        embed = source
    return {
        "id": _random_id(),
        "type": "embed",
        "data": {
            "service": service,
            "source": source,
            "embed": embed,
            "caption": caption,
        },
    }


def quiz_block(quiz_name: str) -> dict[str, Any]:
    """An inline quiz reference.  ``quiz_name`` is the LMS Quiz name/slug."""
    return {
        "id": _random_id(),
        "type": "quiz",
        "data": {"quiz": quiz_name},
    }


def upload_block(file_url: str, file_type: str = "PDF",
                 quizzes: list[str] | None = None) -> dict[str, Any]:
    """An uploaded-file block (video, audio, PDF, image).

    ``file_type`` examples: ``MP4``, ``PDF``, ``mp3``, ``PNG``.
    ``quizzes`` optionally embeds in-video quiz checkpoints.
    """
    return {
        "id": _random_id(),
        "type": "upload",
        "data": {
            "file_url": file_url,
            "file_type": file_type,
            "quizzes": quizzes or [],
        },
    }


def markdown_block(text: str) -> dict[str, Any]:
    """A raw markdown block."""
    return {
        "id": _random_id(),
        "type": "markdown",
        "data": {"text": text},
    }


def build_content(blocks: list[dict[str, Any]]) -> str:
    """Wrap a list of block dicts into a JSON string suitable for the
    ``content`` field of a Course Lesson."""
    import json

    doc = {
        "time": int(time.time() * 1000),
        "blocks": blocks,
        "version": "2.29.0",
    }
    return json.dumps(doc, ensure_ascii=False)


def block_from_text(text: str) -> dict[str, Any]:
    """Convert a single string into a paragraph block (convenience)."""
    return paragraph_block(text)
