"""MCP server exposing Kreuzberg document intelligence utilities.

This module uses the official Kreuzberg MCP server and adds a thin wrapper
around ``extract_document`` to support both local file paths and HTTP(S) URLs.
If a URL is provided, the file is downloaded and processed via
``extract_bytes``. Local paths continue to behave as upstream.
"""

from __future__ import annotations

import asyncio
import base64
import fnmatch
import os
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
from kreuzberg._mcp import server as kreuzberg_server

from backend.config import get_settings
from backend.repository import ChatRepository

mcp = kreuzberg_server.mcp


def run() -> None:  # pragma: no cover - integration entrypoint
    """Execute the Kreuzberg MCP server when launched as a script."""

    kreuzberg_server.main()


# Re-export the highest-level helpers for direct imports.
extract_document = kreuzberg_server.extract_document


def _is_http_url(path: str) -> bool:
    return path.startswith("http://") or path.startswith("https://")


# Minimal repository access to resolve saved attachments by ID
_repository: ChatRepository | None = None
_repository_lock = asyncio.Lock()


def _project_root() -> Path:
    module_path = Path(__file__).resolve()
    return module_path.parents[3]


def _resolve_under(base: Path, p: Path) -> Path:
    if p.is_absolute():
        return p.resolve()
    resolved = (base / p).resolve()
    if not resolved.is_relative_to(base):
        raise ValueError(f"Configured path {resolved} escapes project root {base}")
    return resolved


def _resolve_attachments_dir() -> Path:
    settings = get_settings()
    return _resolve_under(_project_root(), settings.legacy_attachments_dir)


def _resolve_chat_db_path() -> Path:
    settings = get_settings()
    return _resolve_under(_project_root(), settings.chat_database_path)


async def _get_repository() -> ChatRepository:
    global _repository
    if _repository is not None:
        return _repository
    async with _repository_lock:
        if _repository is None:
            repo = ChatRepository(_resolve_chat_db_path())
            await repo.initialize()
            _repository = repo
    return _repository


# Replace upstream tools with wrappers that include proper descriptions.
# Kreuzberg registers these tools but with empty descriptions.
for tool_name in [
    "extract_document",
    "extract_bytes",
    "batch_extract_bytes",
    "batch_extract_document",
    "extract_simple",
]:
    try:
        mcp._tool_manager.remove_tool(tool_name)  # type: ignore[attr-defined]
    except Exception:
        pass


@mcp.tool("extract_document")  # type: ignore[misc]
async def extract_document_urlaware(  # noqa: PLR0913
    file_path: str,
    mime_type: Optional[str] = None,
    force_ocr: bool = False,
    chunk_content: bool = False,
    extract_tables: bool = False,
    extract_entities: bool = False,
    extract_keywords: bool = False,
    ocr_backend: str = "tesseract",
    max_chars: int = 1000,
    max_overlap: int = 200,
    keyword_count: int = 10,
    auto_detect_language: bool = False,
    tesseract_lang: Optional[str] = None,
    tesseract_psm: Optional[int] = None,
    tesseract_output_format: Optional[str] = None,
    enable_table_detection: Optional[bool] = None,
) -> dict[str, Any]:
    """Extract document content from a filesystem path or HTTP(S) URL.

    - Local paths are forwarded to Kreuzberg's ``extract_document``.
    - HTTP(S) URLs are downloaded and passed to ``extract_bytes`` to avoid
      path resolution errors in sandboxed or containerized environments.
    """

    if not _is_http_url(file_path):
        # Prefer direct access for files under the configured uploads directory.
        # This avoids any path restrictions the upstream server might impose and
        # ensures local uploads are always readable by the custom PDF tools.
        try:
            base = _resolve_attachments_dir()
            base_resolved = base.resolve()
            p = Path(file_path)

            candidate: Path | None = None
            if p.is_absolute():
                abs_path = p.resolve()
                if base_resolved in abs_path.parents and abs_path.is_file():
                    candidate = abs_path
            else:
                # Try resolving relative to the uploads directory
                abs_path = (base / p).resolve()
                if (
                    base_resolved in abs_path.parents or abs_path == base_resolved
                ) and abs_path.is_file():
                    candidate = abs_path

            if candidate is not None:
                # Read bytes and delegate to extract_bytes with a sensible mime
                content_bytes = await asyncio.to_thread(candidate.read_bytes)
                # Basic mime inference; default to PDF when extension matches
                inferred_mime = (
                    "application/pdf" if candidate.suffix.lower() == ".pdf" else None
                )
                effective_mime = (
                    mime_type or inferred_mime or "application/octet-stream"
                ).lower()
                content_b64 = base64.b64encode(content_bytes).decode("ascii")

                return await asyncio.to_thread(
                    kreuzberg_server.extract_bytes,
                    content_b64,
                    effective_mime,
                    force_ocr,
                    chunk_content,
                    extract_tables,
                    extract_entities,
                    extract_keywords,
                    ocr_backend,
                    max_chars,
                    max_overlap,
                    keyword_count,
                    auto_detect_language,
                    tesseract_lang,
                    tesseract_psm,
                    tesseract_output_format,
                    enable_table_detection,
                )
        except Exception:
            # Fall back to upstream behavior on any resolution error
            pass

        # Delegate to upstream for other local filesystem paths
        return await asyncio.to_thread(
            kreuzberg_server.extract_document,
            file_path,
            mime_type,
            force_ocr,
            chunk_content,
            extract_tables,
            extract_entities,
            extract_keywords,
            ocr_backend,  # type: ignore[arg-type]
            max_chars,
            max_overlap,
            keyword_count,
            auto_detect_language,
            tesseract_lang,
            tesseract_psm,
            tesseract_output_format,
            enable_table_detection,
        )

    # HTTP(S) flow: fetch bytes, infer mime if needed, and process via extract_bytes
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
            resp = await client.get(file_path)
        resp.raise_for_status()
    except Exception as exc:  # pragma: no cover - network variability
        return {
            "error": f"Failed to download URL: {exc}",
            "file_path": file_path,
        }

    content = resp.content
    if not content:
        return {"error": "Downloaded file was empty", "file_path": file_path}

    inferred_mime = None
    try:
        ct = resp.headers.get("Content-Type") or ""
        inferred_mime = ct.split(";")[0].strip() or None
    except Exception:  # pragma: no cover - lenient
        inferred_mime = None

    effective_mime = (mime_type or inferred_mime or "application/octet-stream").lower()
    content_b64 = base64.b64encode(content).decode("ascii")

    return await asyncio.to_thread(
        kreuzberg_server.extract_bytes,
        content_b64,
        effective_mime,
        force_ocr,
        chunk_content,
        extract_tables,
        extract_entities,
        extract_keywords,
        ocr_backend,
        max_chars,
        max_overlap,
        keyword_count,
        auto_detect_language,
        tesseract_lang,
        tesseract_psm,
        tesseract_output_format,
        enable_table_detection,
    )


@mcp.tool("extract_bytes")  # type: ignore[misc]
async def extract_bytes_tool(  # noqa: PLR0913
    content_base64: str,
    mime_type: str,
    force_ocr: bool = False,
    chunk_content: bool = False,
    extract_tables: bool = False,
    extract_entities: bool = False,
    extract_keywords: bool = False,
    ocr_backend: str = "tesseract",
    max_chars: int = 1000,
    max_overlap: int = 200,
    keyword_count: int = 10,
    auto_detect_language: bool = False,
    tesseract_lang: Optional[str] = None,
    tesseract_psm: Optional[int] = None,
    tesseract_output_format: Optional[str] = None,
    enable_table_detection: Optional[bool] = None,
) -> dict[str, Any]:
    """Extract text and metadata from base64-encoded document bytes.

    Processes document content provided as base64-encoded bytes. Useful for
    uploaded files or in-memory content without filesystem access.

    Args:
        content_base64: Base64-encoded document content
        mime_type: MIME type (e.g., 'application/pdf', 'image/jpeg')
        force_ocr: Force OCR even for text-based documents
        chunk_content: Split content into chunks for RAG applications
        extract_tables: Extract tables from the document
        extract_entities: Extract named entities (PERSON, ORG, DATE, etc.)
        extract_keywords: Extract keywords with relevance scores
        ocr_backend: OCR backend ('tesseract', 'easyocr', 'paddleocr')
        max_chars: Maximum characters per chunk
        max_overlap: Character overlap between chunks
        keyword_count: Number of keywords to extract
        auto_detect_language: Auto-detect document language

    Returns:
        Dictionary with extracted content, metadata, and optional features
    """

    return await asyncio.to_thread(
        kreuzberg_server.extract_bytes,
        content_base64,
        mime_type,
        force_ocr,
        chunk_content,
        extract_tables,
        extract_entities,
        extract_keywords,
        ocr_backend,
        max_chars,
        max_overlap,
        keyword_count,
        auto_detect_language,
        tesseract_lang,
        tesseract_psm,
        tesseract_output_format,
        enable_table_detection,
    )


@mcp.tool("batch_extract_bytes")  # type: ignore[misc]
async def batch_extract_bytes_tool(
    contents_base64: list[str],
    mime_types: list[str],
    force_ocr: bool = False,
    chunk_content: bool = False,
    extract_tables: bool = False,
    extract_entities: bool = False,
    extract_keywords: bool = False,
    ocr_backend: str = "tesseract",
    max_chars: int = 1000,
    max_overlap: int = 200,
    keyword_count: int = 10,
    auto_detect_language: bool = False,
) -> list[dict[str, Any]]:
    """Process multiple documents from base64-encoded bytes concurrently.

    Efficiently batch-processes multiple documents provided as base64-encoded
    bytes, processing them concurrently for optimal performance.

    Args:
        contents_base64: List of base64-encoded document contents
        mime_types: List of MIME types (must match length of contents_base64)
        force_ocr: Force OCR even for text-based documents
        chunk_content: Split content into chunks
        extract_tables: Extract tables from documents
        extract_entities: Extract named entities
        extract_keywords: Extract keywords with scores
        ocr_backend: OCR backend to use
        max_chars: Maximum characters per chunk
        max_overlap: Character overlap between chunks
        keyword_count: Number of keywords to extract
        auto_detect_language: Auto-detect document languages

    Returns:
        List of dictionaries with extraction results, in same order as inputs
    """

    return await asyncio.to_thread(
        kreuzberg_server.batch_extract_bytes,
        contents_base64,
        mime_types,
        force_ocr,
        chunk_content,
        extract_tables,
        extract_entities,
        extract_keywords,
        ocr_backend,
        max_chars,
        max_overlap,
        keyword_count,
        auto_detect_language,
    )


@mcp.tool("batch_extract_document")  # type: ignore[misc]
async def batch_extract_document_tool(
    file_paths: list[str],
    mime_types: Optional[list[str]] = None,
    force_ocr: bool = False,
    chunk_content: bool = False,
    extract_tables: bool = False,
    extract_entities: bool = False,
    extract_keywords: bool = False,
    ocr_backend: str = "tesseract",
    max_chars: int = 1000,
    max_overlap: int = 200,
    keyword_count: int = 10,
    auto_detect_language: bool = False,
) -> list[dict[str, Any]]:
    """Process multiple documents from file paths concurrently.

    Batch-processes multiple document files concurrently for efficient
    extraction from multiple files. Results are returned in the same order
    as the input file paths.

    Args:
        file_paths: List of document file paths
        mime_types: Optional list of MIME types (must match length if provided)
        force_ocr: Force OCR even for text-based documents
        chunk_content: Split content into chunks
        extract_tables: Extract tables from documents
        extract_entities: Extract named entities
        extract_keywords: Extract keywords with scores
        ocr_backend: OCR backend to use
        max_chars: Maximum characters per chunk
        max_overlap: Character overlap between chunks
        keyword_count: Number of keywords to extract
        auto_detect_language: Auto-detect document languages

    Returns:
        List of dictionaries with extraction results, in same order as inputs
    """

    return await asyncio.to_thread(
        kreuzberg_server.batch_extract_document,
        file_paths,
        mime_types,
        force_ocr,
        chunk_content,
        extract_tables,
        extract_entities,
        extract_keywords,
        ocr_backend,
        max_chars,
        max_overlap,
        keyword_count,
        auto_detect_language,
    )


@mcp.tool("extract_simple")  # type: ignore[misc]
async def extract_simple_tool(
    file_path: str,
    mime_type: Optional[str] = None,
) -> str:
    """Simple text extraction with minimal configuration.

    Provides straightforward text extraction from documents without advanced
    features like OCR forcing, table extraction, or entity recognition. Best
    for quick text extraction from standard documents.

    Args:
        file_path: Path to the document file
        mime_type: Optional MIME type hint for the document

    Returns:
        Extracted text content as a string
    """

    return await asyncio.to_thread(
        kreuzberg_server.extract_simple,
        file_path,
        mime_type,
    )


@mcp.tool("extract_saved_attachment")  # type: ignore[misc]
async def extract_saved_attachment(
    attachment_id: str,
    force_ocr: bool = False,
    chunk_content: bool = False,
    extract_tables: bool = False,
    extract_entities: bool = False,
    extract_keywords: bool = False,
    max_chars: int = 1000,
    max_overlap: int = 200,
    keyword_count: int = 10,
    auto_detect_language: bool = False,
) -> str:
    """Extract and return text from a previously saved chat attachment.

    Provide the internal ``attachment_id`` returned by the
    ``download_gmail_attachment`` tool or the uploads API.
    """

    try:
        repo = await _get_repository()
        record = await repo.get_attachment(attachment_id)
    except Exception as exc:  # pragma: no cover - defensive
        return f"Error accessing attachment store: {exc}"

    if not record:
        return f"Attachment not found: {attachment_id}"

    storage_path = record.get("storage_path")
    if not storage_path:
        return "Attachment record missing storage path"

    base = _resolve_attachments_dir()
    abs_path = (base / storage_path).resolve()
    base_resolved = base.resolve()
    if base_resolved not in abs_path.parents and abs_path != base_resolved:
        return "Attachment path escaped storage directory"
    if not abs_path.exists():
        return f"Attachment file missing: {abs_path}"

    # Read bytes in background
    try:
        content_bytes = await asyncio.to_thread(abs_path.read_bytes)
    except Exception as exc:
        return f"Failed to read attachment: {exc}"

    mime_type = (record.get("mime_type") or "application/octet-stream").lower()
    payload = base64.b64encode(content_bytes).decode("ascii")

    try:
        result: dict[str, Any] = kreuzberg_server.extract_bytes(
            content_base64=payload,
            mime_type=mime_type,
            force_ocr=force_ocr,
            chunk_content=chunk_content,
            extract_tables=extract_tables,
            extract_entities=extract_entities,
            extract_keywords=extract_keywords,
            max_chars=max_chars,
            max_overlap=max_overlap,
            keyword_count=keyword_count,
            auto_detect_language=auto_detect_language,
        )
    except Exception as exc:
        return f"Extraction failed: {exc}"

    text = str(result.get("content") or result.get("text") or "").strip()
    if text:
        return text

    # Optional OCR retry if initial attempt had no text and OCR wasn't requested
    if not force_ocr and mime_type == "application/pdf":
        try:
            ocr_result: dict[str, Any] = kreuzberg_server.extract_bytes(
                content_base64=payload,
                mime_type=mime_type,
                force_ocr=True,
                chunk_content=chunk_content,
                extract_tables=extract_tables,
                extract_entities=extract_entities,
                extract_keywords=extract_keywords,
                max_chars=max_chars,
                max_overlap=max_overlap,
                keyword_count=keyword_count,
                auto_detect_language=auto_detect_language,
            )
            ocr_text = str(
                ocr_result.get("content") or ocr_result.get("text") or ""
            ).strip()
            if ocr_text:
                return ocr_text
        except Exception:
            pass

    # Final fallback
    try:
        return content_bytes.decode("utf-8")
    except Exception:
        return f"[Binary content; {len(content_bytes)} bytes; mime={mime_type}]"


def _guess_mime_from_suffix(path: Path) -> str:
    suf = path.suffix.lower()
    if suf == ".pdf":
        return "application/pdf"
    if suf in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return f"image/{suf.lstrip('.').replace('jpg', 'jpeg')}"
    if suf in {".txt", ".md"}:
        return "text/plain"
    return "application/octet-stream"


def _file_info(base: Path, p: Path) -> dict[str, Any]:
    stat = p.stat()
    rel = str(p.relative_to(base))
    edt_iso = (
        datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        .astimezone(timezone.utc)
        .isoformat()
    )
    return {
        "relative_path": rel,
        "absolute_path": str(p),
        "size_bytes": stat.st_size,
        "modified_at": edt_iso,
        "mime_type": _guess_mime_from_suffix(p),
    }


def _extract_attachment_id(relative_path: str) -> str | None:
    """Derive the attachment_id from the stored filename when possible."""

    name = Path(relative_path).name
    stem = Path(name).stem
    if "__" in stem:
        stem = stem.split("__", 1)[0]
    candidate = stem.lower()
    if len(candidate) == 32 and all(ch in string.hexdigits for ch in candidate):
        return candidate
    return None


@mcp.tool("list_upload_paths")  # type: ignore[misc]
async def list_upload_paths(
    subdir: Optional[str] = None,
    pattern: Optional[str] = None,
    max_results: int = 200,
    include_dirs: bool = False,
) -> list[dict[str, Any]]:
    """List files under the configured uploads directory.

    - `subdir`: optional path relative to `data/uploads` to scope the listing
    - `pattern`: optional glob or substring to filter names (e.g., `*.pdf` or `report`)
    - `max_results`: limit the number of entries returned (most recent first)
    - `include_dirs`: include directories in results (default False)
    """

    base = _resolve_attachments_dir().resolve()
    start = base
    if subdir:
        p = (base / subdir).resolve()
        if base not in p.parents and p != base:
            return [
                {
                    "error": "Subdirectory escapes uploads base",
                    "subdir": subdir,
                }
            ]
        start = p

    entries: list[tuple[Path, os.stat_result, bool]] = []
    for root, dirs, files in os.walk(start):
        root_path = Path(root)
        # Consider directories only if requested
        if include_dirs:
            for d in dirs:
                p = (root_path / d).resolve()
                try:
                    st = p.stat()
                except FileNotFoundError:
                    continue
                entries.append((p, st, True))
        # Files
        for f in files:
            p = (root_path / f).resolve()
            try:
                st = p.stat()
            except FileNotFoundError:
                continue
            entries.append((p, st, False))

    # Filter by pattern
    results: list[dict[str, Any]] = []
    try:
        repository: ChatRepository | None = await _get_repository()
    except Exception:  # pragma: no cover - defensive fallback
        repository = None
    for p, st, is_dir in entries:
        if base not in p.parents and p != base:
            continue
        name_rel = str(p.relative_to(base))
        if pattern:
            if any(ch in pattern for ch in "*?[]"):
                if not fnmatch.fnmatch(name_rel, pattern):
                    continue
            else:
                if pattern.lower() not in name_rel.lower():
                    continue
        if is_dir and not include_dirs:
            continue
        if is_dir:
            info = {
                "relative_path": name_rel,
                "absolute_path": str(p),
                "size_bytes": st.st_size,
                "modified_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
                .astimezone(timezone.utc)
                .isoformat(),
                "type": "directory",
            }
        else:
            info = _file_info(base, p)
            info["type"] = "file"
            if repository is not None:
                attachment_id = _extract_attachment_id(name_rel)
                if attachment_id is not None:
                    try:
                        record = await repository.get_attachment(attachment_id)
                    except Exception:  # pragma: no cover - defensive
                        record = None
                else:
                    record = None
                if record:
                    info["attachment_id"] = attachment_id
                    session_id = record.get("session_id")
                    if isinstance(session_id, str):
                        info["session_id"] = session_id
                    metadata = record.get("metadata")
                    if isinstance(metadata, dict):
                        original = metadata.get("filename") or metadata.get(
                            "original_filename"
                        )
                        if original:
                            info["original_filename"] = original
                    mime = record.get("mime_type")
                    if isinstance(mime, str) and mime:
                        info["mime_type"] = mime
                    created = record.get("created_at")
                    if isinstance(created, str):
                        info["created_at"] = created
                    expires = record.get("expires_at")
                    if isinstance(expires, str):
                        info["expires_at"] = expires
        results.append(info)

    # Sort by mtime desc and limit
    results.sort(key=lambda r: r.get("modified_at", ""), reverse=True)
    if max_results and max_results > 0:
        results = results[:max_results]

    # Enrich with repository metadata (original filename, URLs) when available
    try:
        repo = await _get_repository()
        for item in results:
            if item.get("type") != "file":
                continue
            rel = item.get("relative_path")
            if not isinstance(rel, str):
                continue
            # Normalize to DB format
            storage_path = str(Path(rel))
            record = await repo.get_attachment_by_storage_path(storage_path)
            if record:
                meta = record.get("metadata") or {}
                original = None
                if isinstance(meta, dict):
                    original = meta.get("filename")
                if original:
                    item["original_filename"] = original
                    # Provide a friendly default label
                    item.setdefault("name", original)
                else:
                    item.setdefault("name", Path(rel).name)
                # Attach a few useful fields
                item["attachment_id"] = record.get("attachment_id")
                item["session_id"] = record.get("session_id")
                item["display_url"] = record.get("display_url")
                item["delivery_url"] = record.get("delivery_url")
                item["created_at"] = record.get("created_at")
                item["expires_at"] = record.get("expires_at")
                item["last_used_at"] = record.get("last_used_at")
            else:
                # Fallback name is the basename
                item.setdefault("name", Path(rel).name)
    except Exception:
        # Non-fatal: listing still works without metadata
        for item in results:
            if item.get("type") == "file":
                rel = item.get("relative_path")
                if isinstance(rel, str):
                    item.setdefault("name", Path(rel).name)
    return results


@mcp.tool("search_upload_paths")  # type: ignore[misc]
async def search_upload_paths(
    query: str,
    session_id: Optional[str] = None,
    max_results: int = 100,
) -> list[dict[str, Any]]:
    """Search for files in uploads by filename substring or glob.

    - `session_id`: if provided, limits search to that subdirectory.
    - `query`: substring or glob pattern (e.g., `*.pdf`, `invoice`).
    """

    subdir = session_id or None
    return await list_upload_paths(
        subdir=subdir, pattern=query, max_results=max_results
    )


__all__ = [
    "mcp",
    "run",
    "extract_document",
    "extract_bytes",
    "batch_extract_bytes",
    "batch_extract_document",
    "extract_simple",
    "list_upload_paths",
    "search_upload_paths",
]

# Re-export underlying Kreuzberg functions for direct Python imports
extract_bytes = kreuzberg_server.extract_bytes
batch_extract_bytes = kreuzberg_server.batch_extract_bytes
batch_extract_document = kreuzberg_server.batch_extract_document
extract_simple = kreuzberg_server.extract_simple


if __name__ == "__main__":  # pragma: no cover - CLI helper
    run()
