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

from fastmcp import FastMCP
import httpx
import kreuzberg
from kreuzberg import ExtractionConfig
from kreuzberg._mcp import server as kreuzberg_server

# Optional imports for sanitization
try:
    import pandas as pd
except ImportError:
    pd = None  # type: ignore

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore

from backend.config import get_settings
from backend.repository import ChatRepository

# Default port for HTTP transport
DEFAULT_HTTP_PORT = 9007

mcp = FastMCP.as_proxy(
    backend=kreuzberg_server.mcp,
    name="custom-pdf",
    on_duplicate_tools="replace",
)


def run(
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = DEFAULT_HTTP_PORT,
) -> None:  # pragma: no cover - integration entrypoint
    """Run the MCP server with the specified transport."""

    if transport == "streamable-http":
        mcp.run(
            transport="streamable-http",
            host=host,
            port=port,
            json_response=True,
            stateless_http=True,
            uvicorn_config={"access_log": False},
        )
    else:
        mcp.run(transport="stdio")


# Re-export the highest-level helpers for direct imports.
extract_document = kreuzberg_server.extract_document


def _is_http_url(path: str) -> bool:
    return path.startswith("http://") or path.startswith("https://")


def _normalize_gdrive_url(url: str) -> str:
    """Transform Google Drive URLs to direct download format.

    Handles these formats:
    - https://drive.google.com/file/d/{id}/view?... → direct download
    - https://drive.google.com/open?id={id} → direct download
    - https://drive.google.com/uc?id={id} → add export=download
    """
    if "drive.google.com" not in url:
        return url

    # Extract file ID from various formats
    file_id = None

    # Format: /file/d/{id}/view
    if "/file/d/" in url:
        parts = url.split("/file/d/")[1].split("/")[0]
        file_id = parts.split("?")[0]
    # Format: open?id={id}
    elif "open?id=" in url:
        file_id = url.split("open?id=")[1].split("&")[0]
    # Format: uc?id={id}
    elif "uc?id=" in url:
        file_id = url.split("uc?id=")[1].split("&")[0]

    if file_id:
        return f"https://drive.google.com/uc?export=download&id={file_id}"

    return url


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


def _sanitize_result(obj: Any) -> Any:
    """Recursively sanitize extraction results for JSON serialization.

    Converts pandas DataFrames to Markdown and PIL Images to string descriptions.
    """
    if pd is not None and isinstance(obj, pd.DataFrame):
        return obj.to_markdown()

    if Image is not None and isinstance(obj, Image.Image):
        return f"<Image format={obj.format} size={obj.size} mode={obj.mode}>"

    if isinstance(obj, dict):
        return {k: _sanitize_result(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_result(v) for v in obj]

    return obj


def _sanitize_table_data(table: Any) -> dict[str, Any]:
    """Convert TableData to a JSON-serializable dictionary."""
    # table might be TableData object or dict
    if isinstance(table, dict):
        page_number = table.get("page_number")
        text = table.get("text")
        df = table.get("df")
        cropped_image = table.get("cropped_image")
    else:
        page_number = getattr(table, "page_number", None)
        text = getattr(table, "text", None)
        df = getattr(table, "df", None)
        cropped_image = getattr(table, "cropped_image", None)

    data = {"page_number": page_number, "text": text}
    if df is not None:
        if pd is not None and isinstance(df, pd.DataFrame):
            data["markdown"] = df.to_markdown()
        else:
            data["markdown"] = str(df)

    if cropped_image is not None:
        if Image is not None and isinstance(cropped_image, Image.Image):
            data["image_info"] = (
                f"<Image size={cropped_image.size} format={cropped_image.format}>"
            )
        else:
            data["image_info"] = str(cropped_image)

    return data


def _sanitize_extracted_image(img: Any) -> dict[str, Any]:
    """Convert ExtractedImage to a JSON-serializable dictionary."""
    # img might be ExtractedImage object or dict
    if isinstance(img, dict):
        return _sanitize_result(img)

    return {
        "format": getattr(img, "format", None),
        "filename": getattr(img, "filename", None),
        "page_number": getattr(img, "page_number", None),
        "dimensions": getattr(img, "dimensions", None),
        "colorspace": getattr(img, "colorspace", None),
        "description": getattr(img, "description", None),
        # Omit raw data bytes to keep response size manageable
        "data_size_bytes": len(img.data) if hasattr(img, "data") and img.data else 0,
    }


def _convert_extraction_result(result: Any) -> dict[str, Any]:
    """Convert ExtractionResult (or dict) to a JSON-serializable dictionary."""
    if isinstance(result, dict):
        # Already a dict (maybe from upstream or error), sanitize recursively
        return _sanitize_result(result)

    # Assume it's ExtractionResult
    if not hasattr(result, "content"):
        # Fallback for unknown types
        return _sanitize_result(result)

    data = {
        "content": result.content,
        "mime_type": result.mime_type,
        "chunks": result.chunks,
        "detected_languages": result.detected_languages,
        "document_type": result.document_type,
        "document_type_confidence": result.document_type_confidence,
    }

    if result.metadata:
        data["metadata"] = _sanitize_result(result.metadata)

    if result.tables:
        data["tables"] = [_sanitize_table_data(t) for t in result.tables]

    if result.images:
        data["images"] = [_sanitize_extracted_image(i) for i in result.images]

    if result.entities:
        data["entities"] = _sanitize_result(result.entities)

    if result.keywords:
        data["keywords"] = result.keywords

    return data


@mcp.tool("extract_document")  # type: ignore[misc]
async def extract_document_urlaware(  # noqa: PLR0913
    document_url_or_path: str,
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
    """**PRIMARY TOOL:** Extract document content from filesystem paths or URLs.

    This is the recommended tool for most document extraction tasks. Use this when
    you have a file path (local) or web link (Google Drive, HTTP/HTTPS URLs).

    **When to use:**
    - Extracting from local filesystem paths
    - Extracting from web URLs including Google Drive share links
    - Any scenario where you have a document path or URL

    **Universal approach:**
    - URLs are downloaded automatically
    - Local files are read directly
    - Everything is converted to bytes and processed consistently
    - No file ever stays on disk in base64 - only temporary in-memory conversion

    **Use extract_bytes instead only if:** you already have document data loaded
    in memory as base64. Otherwise, this tool handles everything for you.

    Args:
        document_url_or_path: Local filesystem path OR web URL (http/https including Google Drive)
    """

    # Build config
    config = _build_extraction_config(
        force_ocr=force_ocr,
        chunk_content=chunk_content,
        extract_tables=extract_tables,
        extract_entities=extract_entities,
        extract_keywords=extract_keywords,
        ocr_backend=ocr_backend,
        max_chars=max_chars,
        max_overlap=max_overlap,
        keyword_count=keyword_count,
        auto_detect_language=auto_detect_language,
        tesseract_lang=tesseract_lang,
        tesseract_psm=tesseract_psm,
        tesseract_output_format=tesseract_output_format,
        enable_table_detection=enable_table_detection,
    )

    # Handle file:// URIs by stripping the scheme
    if document_url_or_path.startswith("file://"):
        document_url_or_path = document_url_or_path[7:]

    if not _is_http_url(document_url_or_path):
        # Universal local file handling: read any accessible file directly
        try:
            p = Path(document_url_or_path)
            # Try as absolute path first
            if p.is_absolute() and p.is_file():
                content_bytes = await asyncio.to_thread(p.read_bytes)
                inferred_mime = _guess_mime_from_suffix(p)
                effective_mime = (
                    mime_type or inferred_mime or "application/octet-stream"
                ).lower()

                result = await kreuzberg.extract_bytes(
                    content_bytes, effective_mime, config
                )
                return _convert_extraction_result(result)

            # Try relative to uploads directory
            if not p.is_absolute():
                base = _resolve_attachments_dir()
                abs_path = (base / p).resolve()
                if abs_path.is_file():
                    content_bytes = await asyncio.to_thread(abs_path.read_bytes)
                    inferred_mime = _guess_mime_from_suffix(abs_path)
                    effective_mime = (
                        mime_type or inferred_mime or "application/octet-stream"
                    ).lower()

                    result = await kreuzberg.extract_bytes(
                        content_bytes, effective_mime, config
                    )
                    return _convert_extraction_result(result)
        except Exception:
            # Fall back to upstream on any read error
            pass

        # Final fallback: delegate to upstream Kreuzberg (using extract_file directly)
        try:
            result = await kreuzberg.extract_file(
                document_url_or_path, mime_type, config
            )
            return _convert_extraction_result(result)
        except Exception as e:
            return {"error": str(e)}

    # Universal HTTP(S) flow: download from any URL and process via extract_bytes
    # Normalize Google Drive URLs to direct download format
    if "drive.google.com" in document_url_or_path:
        document_url_or_path = _normalize_gdrive_url(document_url_or_path)

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
            resp = await client.get(document_url_or_path)
        resp.raise_for_status()
    except Exception as exc:  # pragma: no cover - network variability
        return {
            "error": f"Failed to download URL: {exc}",
            "file_path": document_url_or_path,
        }

    content = resp.content
    if not content:
        return {"error": "Downloaded file was empty", "file_path": document_url_or_path}

    inferred_mime = None
    try:
        ct = resp.headers.get("Content-Type") or ""
        inferred_mime = ct.split(";")[0].strip() or None
    except Exception:  # pragma: no cover - lenient
        inferred_mime = None

    effective_mime = (mime_type or inferred_mime or "application/octet-stream").lower()

    result = await kreuzberg.extract_bytes(content, effective_mime, config)
    return _convert_extraction_result(result)


async def extract_bytes(
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
    """Safe extract_bytes function for internal use."""
    config = _build_extraction_config(
        force_ocr=force_ocr,
        chunk_content=chunk_content,
        extract_tables=extract_tables,
        extract_entities=extract_entities,
        extract_keywords=extract_keywords,
        ocr_backend=ocr_backend,
        max_chars=max_chars,
        max_overlap=max_overlap,
        keyword_count=keyword_count,
        auto_detect_language=auto_detect_language,
        tesseract_lang=tesseract_lang,
        tesseract_psm=tesseract_psm,
        tesseract_output_format=tesseract_output_format,
        enable_table_detection=enable_table_detection,
    )

    content_bytes = base64.b64decode(content_base64)
    result = await kreuzberg.extract_bytes(content_bytes, mime_type, config)
    return _convert_extraction_result(result)


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
    """**ADVANCED:** Extract text from base64-encoded document data already in memory.

    **Use extract_document instead** for files on disk or URLs. This tool is only
    needed when you already have document data loaded in memory as base64.

    **When to use:**
    - Processing file data received from an API upload endpoint
    - Document bytes already loaded in memory from another source
    - Building custom pipelines that work with in-memory data

    **Do NOT use if:**
    - You have a file path → use extract_document
    - You have a URL (Google Drive, HTTP) → use extract_document
    - The file is on disk anywhere → use extract_document

    This tool exists for specialized cases. For typical document extraction,
    extract_document is simpler and handles downloading/loading automatically.

    Args:
        content_base64: Base64-encoded document content (not a path or URL)
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
    return await extract_bytes(
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
    """**PERFORMANCE OPTIMIZATION:** Process multiple in-memory documents concurrently.

    Batch-processes multiple documents already loaded as base64 in memory.
    Processing happens concurrently for speed. Use batch_extract_document instead
    if you have file paths or URLs.

    **When to use:**
    - Multiple documents already in memory as base64
    - Need concurrent processing for performance
    - Specialized pipelines with pre-loaded data

    **Use batch_extract_document instead if:** you have file paths or URLs.

    Args:
        contents_base64: List of base64-encoded document contents (not paths)
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

    # Build config
    config = _build_extraction_config(
        force_ocr=force_ocr,
        chunk_content=chunk_content,
        extract_tables=extract_tables,
        extract_entities=extract_entities,
        extract_keywords=extract_keywords,
        ocr_backend=ocr_backend,
        max_chars=max_chars,
        max_overlap=max_overlap,
        keyword_count=keyword_count,
        auto_detect_language=auto_detect_language,
    )

    # Decode base64 and pair with mime_types
    contents = []
    for b64, mime in zip(contents_base64, mime_types):
        contents.append((base64.b64decode(b64), mime))

    results = await kreuzberg.batch_extract_bytes(contents, config)
    return [_convert_extraction_result(r) for r in results]


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
    """**PERFORMANCE OPTIMIZATION:** Process multiple documents from paths/URLs concurrently.

    Batch version of extract_document for processing many files efficiently.
    Documents are processed concurrently for speed. Use this when you need to
    extract from multiple files at once.

    **When to use:**
    - Processing multiple local files simultaneously
    - Extracting from a list of URLs
    - Need faster throughput than calling extract_document repeatedly

    **Performance benefit:** Concurrent processing is significantly faster than
    calling extract_document in a loop.

    Args:
        file_paths: List of document file paths or HTTP(S) URLs
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

    # Build config
    config = _build_extraction_config(
        force_ocr=force_ocr,
        chunk_content=chunk_content,
        extract_tables=extract_tables,
        extract_entities=extract_entities,
        extract_keywords=extract_keywords,
        ocr_backend=ocr_backend,
        max_chars=max_chars,
        max_overlap=max_overlap,
        keyword_count=keyword_count,
        auto_detect_language=auto_detect_language,
    )

    # Note: mime_types argument is ignored as kreuzberg.batch_extract_file doesn't support it per file
    results = await kreuzberg.batch_extract_file(file_paths, config)
    return [_convert_extraction_result(r) for r in results]


@mcp.tool("extract_simple")  # type: ignore[misc]
async def extract_simple_tool(
    file_path: str,
    mime_type: Optional[str] = None,
) -> str:
    """**SIMPLIFIED:** Quick text extraction without advanced features.

    Lightweight version of extract_document that only extracts plain text.
    No OCR control, no table extraction, no entity recognition. Use this
    when you just need the text content quickly.

    **When to use:**
    - Only need plain text, no metadata
    - Processing simple, standard documents
    - Want simpler output (string vs dictionary)

    **Use extract_document instead if you need:**
    - OCR control for scanned documents
    - Table extraction
    - Entity recognition
    - Keyword extraction
    - Chunking for RAG applications
    - More detailed metadata

    Args:
        file_path: Path to the document file or HTTP(S) URL
        mime_type: Optional MIME type hint for the document

    Returns:
        Extracted text content as a simple string
    """

    result = await kreuzberg.extract_file(file_path, mime_type)
    return result.content


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
    """**CONVENIENCE:** Extract text from attachments saved in the chat system.

    Use this when you have an attachment_id from a previous upload or Gmail
    download. This tool looks up the attachment in the database and extracts
    its content automatically.

    **When to use:**
    - Have an attachment_id from download_gmail_attachment
    - Have an attachment_id from the uploads API
    - Need to re-process a previously uploaded file

    **How it works:**
    1. Looks up attachment metadata in database by ID
    2. Locates the file in the uploads directory
    3. Extracts and returns the text content
    4. Auto-retries with OCR if initial extraction returns no text

    **Use extract_document instead if:** you have the file path directly.

    Args:
        attachment_id: Internal attachment ID (32-character hex string)
        force_ocr: Force OCR even for text-based documents
        chunk_content: Split content into chunks
        extract_tables: Extract tables from document
        extract_entities: Extract named entities
        extract_keywords: Extract keywords with scores
        max_chars: Maximum characters per chunk
        max_overlap: Character overlap between chunks
        keyword_count: Number of keywords to extract
        auto_detect_language: Auto-detect document language

    Returns:
        Extracted text as a string, or error message if extraction fails
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

    # Build config
    config = _build_extraction_config(
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

    try:
        result_obj = await kreuzberg.extract_bytes(
            content=content_bytes, mime_type=mime_type, config=config
        )
        # Convert to dict for compatibility with existing logic below
        result = _convert_extraction_result(result_obj)
    except Exception as exc:
        return f"Extraction failed: {exc}"

    text = str(result.get("content") or result.get("text") or "").strip()
    if text:
        return text

    # Optional OCR retry if initial attempt had no text and OCR wasn't requested
    if not force_ocr and mime_type == "application/pdf":
        try:
            ocr_config = _build_extraction_config(
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
            ocr_result_obj = await kreuzberg.extract_bytes(
                content=content_bytes, mime_type=mime_type, config=ocr_config
            )
            ocr_result = _convert_extraction_result(ocr_result_obj)
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


def _build_extraction_config(
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
) -> ExtractionConfig:
    """Build ExtractionConfig from tool arguments."""
    # Map arguments to config
    # Note: Some arguments might need adjustment based on ExtractionConfig definition

    # Create config with available arguments
    config = ExtractionConfig(
        force_ocr=force_ocr,
        chunk_content=chunk_content,
        extract_tables=extract_tables,
        extract_entities=extract_entities,
        extract_keywords=extract_keywords,
        ocr_backend=ocr_backend,  # type: ignore
        max_chars=max_chars,
        max_overlap=max_overlap,
        keyword_count=keyword_count,
        auto_detect_language=auto_detect_language,
    )

    # Set optional fields if they exist in ExtractionConfig and are provided
    # (This depends on exact ExtractionConfig definition, assuming standard fields match)

    return config


if __name__ == "__main__":  # pragma: no cover - CLI helper
    import argparse

    parser = argparse.ArgumentParser(description="PDF MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="Transport protocol to use",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind HTTP server to",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_HTTP_PORT,
        help="Port for HTTP server",
    )
    args = parser.parse_args()
    run(args.transport, args.host, args.port)


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
# extract_bytes is now our safe wrapper defined above
# extract_bytes = kreuzberg_server.extract_bytes
batch_extract_bytes = kreuzberg_server.batch_extract_bytes
batch_extract_document = kreuzberg_server.batch_extract_document
extract_simple = kreuzberg_server.extract_simple


if __name__ == "__main__":  # pragma: no cover - CLI helper
    run()
