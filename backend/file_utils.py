"""Validation and lifecycle helpers for uploaded document files."""

import asyncio
import logging
import os
import uuid

import aiofiles
from fastapi import HTTPException, UploadFile

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 10 * 1024 * 1024
READ_CHUNK_SIZE = 1024 * 1024
MIME_HEADER_SIZE = 2048


def _positive_int_from_env(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be a positive integer") from error
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive integer")
    return value


MAX_UPLOAD_STORAGE_BYTES = (
    _positive_int_from_env("MAX_UPLOAD_STORAGE_MB", 5 * 1024) * 1024 * 1024
)
MAX_UPLOAD_FILES = _positive_int_from_env("MAX_UPLOAD_FILES", 10_000)


ALLOWED_MIMES = frozenset(
    {"application/pdf", "image/png", "image/jpeg", "text/plain"}
)
MIME_EXTENSIONS = {
    "application/pdf": frozenset({".pdf"}),
    "text/plain": frozenset({".txt"}),
    "image/png": frozenset({".png"}),
    "image/jpeg": frozenset({".jpg", ".jpeg"}),
}
UPLOAD_DIR = "uploads"
_upload_write_lock = asyncio.Lock()


def detect_mime_from_header(header: bytes) -> str | None:
    """Detect supported file types from signatures without trusting request headers."""
    if header.startswith(b"%PDF-"):
        return "application/pdf"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"

    if b"\x00" in header:
        return None
    try:
        header.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return "text/plain"


def detect_mime_with_libmagic(header: bytes) -> str | None:
    """Use libmagic when available, falling back cleanly when it is not."""
    try:
        import magic
    except ImportError:
        logger.info("python-magic is unavailable; using signature-based detection")
        return None

    try:
        detected_mime = magic.from_buffer(header, mime=True)
    except Exception as error:
        logger.warning("libmagic could not inspect an upload: %s", error)
        return None

    return detected_mime if detected_mime in ALLOWED_MIMES else None


async def validate_file(file: UploadFile) -> str:
    """Validate upload size, content signature, and filename extension."""
    try:
        file.file.seek(0, os.SEEK_END)
        file_size = file.file.tell()
        await file.seek(0)
    except (OSError, ValueError) as error:
        logger.warning("Could not determine upload size: %s", error)
        raise HTTPException(
            status_code=400,
            detail="Could not inspect uploaded file",
        ) from error
    if file_size == 0:
        raise HTTPException(status_code=400, detail="Empty files are not allowed")

    if file_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (Max 10MB)")

    try:
        header = await file.read(MIME_HEADER_SIZE)
        await file.seek(0)
    except (OSError, ValueError) as error:
        logger.warning("Could not read upload header: %s", error)
        raise HTTPException(
            status_code=400,
            detail="Could not determine file type",
        ) from error

    detected_mime = await asyncio.to_thread(detect_mime_with_libmagic, header)
    mime_type = detected_mime or detect_mime_from_header(header)

    if mime_type is None or mime_type not in ALLOWED_MIMES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported or undetectable file type",
        )

    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    expected_exts = MIME_EXTENSIONS[mime_type]

    if ext not in expected_exts:
        raise HTTPException(
            status_code=400,
            detail=f"File extension '{ext}' does not match detected type '{mime_type}'",
        )

    return mime_type


def _upload_file_size(file: UploadFile) -> int:
    try:
        file.file.seek(0, os.SEEK_END)
        file_size = file.file.tell()
        file.file.seek(0)
    except (OSError, ValueError) as error:
        raise HTTPException(
            status_code=400,
            detail="Could not inspect uploaded file",
        ) from error
    return file_size


def _stored_upload_usage(directory: str) -> tuple[int, int]:
    try:
        entries = os.scandir(directory)
    except FileNotFoundError:
        return 0, 0

    with entries:
        total_bytes = 0
        total_files = 0
        for entry in entries:
            try:
                if entry.is_file(follow_symlinks=False):
                    total_bytes += entry.stat(follow_symlinks=False).st_size
                    total_files += 1
            except FileNotFoundError:
                continue
        return total_bytes, total_files


def _replaceable_file_usage(file_path: str | None) -> tuple[int, int]:
    if not file_path:
        return 0, 0
    try:
        return os.path.getsize(resolve_file_path(file_path)), 1
    except (FileNotFoundError, OSError, PermissionError):
        return 0, 0


async def save_upload_file(
    file: UploadFile,
    directory: str = UPLOAD_DIR,
    *,
    replaced_file_path: str | None = None,
) -> str:
    """Persist an upload atomically while enforcing the global storage quota."""
    filename = file.filename or "unknown"
    file_extension = os.path.splitext(filename)[1].lower() or ".bin"
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = os.path.join(directory, unique_filename)
    temporary_path = f"{file_path}.part"
    incoming_bytes = _upload_file_size(file)

    async with _upload_write_lock:
        try:
            await asyncio.to_thread(os.makedirs, directory, exist_ok=True)
            stored_bytes, stored_files = await asyncio.to_thread(
                _stored_upload_usage, directory
            )
            replaceable_bytes, replaceable_files = await asyncio.to_thread(
                _replaceable_file_usage, replaced_file_path
            )
            projected_bytes = stored_bytes - replaceable_bytes + incoming_bytes
            projected_files = stored_files - replaceable_files + 1
            if projected_bytes > MAX_UPLOAD_STORAGE_BYTES:
                raise HTTPException(
                    status_code=507,
                    detail="Upload storage quota exceeded",
                )
            if projected_files > MAX_UPLOAD_FILES:
                raise HTTPException(
                    status_code=507,
                    detail="Upload file count quota exceeded",
                )

            async with aiofiles.open(temporary_path, "wb") as buffer:
                while content := await file.read(READ_CHUNK_SIZE):
                    await buffer.write(content)
            await file.seek(0)
            await asyncio.to_thread(os.replace, temporary_path, file_path)
        except HTTPException:
            raise
        except Exception as error:
            logger.exception("Could not save uploaded file")
            raise HTTPException(
                status_code=500,
                detail="File save failed",
            ) from error
        finally:
            try:
                await asyncio.to_thread(os.remove, temporary_path)
            except FileNotFoundError:
                pass
            except OSError as cleanup_error:
                logger.warning(
                    "Could not remove incomplete upload %s: %s",
                    temporary_path,
                    cleanup_error,
                )

    return file_path


def resolve_file_path(file_path: str) -> str:
    """Resolve an existing path and ensure it remains inside ``UPLOAD_DIR``."""
    if not file_path:
        raise FileNotFoundError("Empty file path")

    if os.path.isabs(file_path):
        candidate_path = file_path
    else:
        normalized_path = os.path.normpath(file_path)
        normalized_upload_dir = os.path.normpath(UPLOAD_DIR)
        already_prefixed = (
            normalized_path == normalized_upload_dir
            or normalized_path.startswith(normalized_upload_dir + os.sep)
        )
        if already_prefixed:
            candidate_path = normalized_path
        else:
            candidate_path = os.path.join(UPLOAD_DIR, normalized_path)
    abs_path = os.path.realpath(os.path.abspath(candidate_path))
    base_dir = os.path.realpath(os.path.abspath(UPLOAD_DIR))

    try:
        is_inside_upload_dir = os.path.commonpath([base_dir, abs_path]) == base_dir
    except ValueError:
        is_inside_upload_dir = False

    if not is_inside_upload_dir:
        raise PermissionError("Access denied: Path is outside the uploads directory")

    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"File not found: {abs_path}")

    return abs_path


def delete_upload_file(file_path: str) -> bool:
    """Delete a stored upload, returning whether a file was removed."""
    try:
        abs_path = resolve_file_path(file_path)
    except FileNotFoundError:
        return False
    except (OSError, PermissionError):
        logger.exception("Could not resolve upload for deletion: %s", file_path)
        return False

    try:
        os.remove(abs_path)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        logger.exception("Could not delete upload: %s", abs_path)
        return False
