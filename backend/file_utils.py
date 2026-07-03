
import os
import uuid
import aiofiles
from fastapi import UploadFile, HTTPException

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_MIMES = ["application/pdf", "image/png", "image/jpeg", "text/plain"]
UPLOAD_DIR = "uploads"


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


async def validate_file(file: UploadFile) -> str:
    """
    Validates file size and type.
    Returns the detected file type if valid, raises HTTPException otherwise.
    """
    # 1. Validate File Size
    # We need to read the file to check size properly if content-length is forged,
    # but for typical fast checks, we can try to rely on stream or read chunks.
    # However, to be safe and simple given the constraints, we read it.
    # CAUTION: This consumes memory. For very large files, stream processing is better.
    # Given MAX_FILE_SIZE is 10MB, reading into memory is acceptable.
    
    # Check size by seeking (blocking but fast for SpooledTempFile) or reading
    file.file.seek(0, 2)
    file_size = file.file.tell()
    await file.seek(0)
    
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (Max 10MB)")

    # 2. Validate File Type (Magic Numbers)
    try:
        # Check first 2048 bytes
        header = await file.read(2048)
        await file.seek(0)

        mime_type = None
        try:
            import magic
            # magic.from_buffer returns string like "PDF document, version 1.4"
            # magic.Magic(mime=True) returns "application/pdf"
            detected_mime = magic.from_buffer(header, mime=True)
            if detected_mime in ALLOWED_MIMES:
                mime_type = detected_mime
        except Exception as e:
            print(f"Magic detection unavailable: {e}")

        if mime_type is None:
            mime_type = detect_mime_from_header(header)
            
    except Exception as e:
        print(f"Magic validation warning: {e}")
        raise HTTPException(status_code=400, detail="Could not determine file type")

    mime_to_exts = {
        "application/pdf": [".pdf"],
        "text/plain": [".txt"],
        "image/png": [".png"],
        "image/jpeg": [".jpg", ".jpeg"]
    }

    if mime_type not in ALLOWED_MIMES:
        raise HTTPException(status_code=400, detail="Unsupported or undetectable file type")

    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    expected_exts = mime_to_exts.get(mime_type, [])
    
    if ext not in expected_exts:
        raise HTTPException(status_code=400, detail=f"File extension '{ext}' does not match detected type '{mime_type}'")

    return mime_type

async def save_upload_file(file: UploadFile, directory: str = UPLOAD_DIR) -> str:
    """
    Saves an uploaded file to the specified directory with a unique name.
    Async version to prevent blocking code in route handlers.
    """
    os.makedirs(directory, exist_ok=True)
    
    filename = file.filename or "unknown"
    file_extension = os.path.splitext(filename)[1]
    if not file_extension:
        file_extension = ".bin" # Fallback
        
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = os.path.join(directory, unique_filename)
    
    try:
        async with aiofiles.open(file_path, "wb") as buffer:
            while content := await file.read(1024 * 1024):  # Read in 1MB chunks
                await buffer.write(content)
        # Reset cursor for potential future reads (e.g. valid chains, though usually not needed after save)
        await file.seek(0)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File save failed: {str(e)}")
        
    return file_path

def resolve_file_path(file_path: str) -> str:
    """
    Resolves a file path to an absolute path and verifies it exists.
    Handles relative paths within UPLOAD_DIR.
    """
    if not file_path:
        raise FileNotFoundError("Empty file path")
        
    if os.path.isabs(file_path):
        candidate_path = file_path
    else:
        normalized_path = os.path.normpath(file_path)
        normalized_upload_dir = os.path.normpath(UPLOAD_DIR)
        if normalized_path == normalized_upload_dir or normalized_path.startswith(normalized_upload_dir + os.sep):
            candidate_path = normalized_path
        else:
            candidate_path = os.path.join(UPLOAD_DIR, normalized_path)
    abs_path = os.path.abspath(candidate_path)
    
    # Secure resolution to prevent path traversal
    abs_path = os.path.realpath(abs_path)
    base_dir = os.path.realpath(os.path.abspath(UPLOAD_DIR))
    
    if os.path.commonpath([base_dir, abs_path]) != base_dir:
        raise PermissionError("Access denied: Path is outside the uploads directory")
        
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"File not found: {abs_path}")
        
    return abs_path


def delete_upload_file(file_path: str) -> None:
    """
    Deletes a stored upload only after resolving it inside UPLOAD_DIR.
    Missing files are ignored so database cleanup can still complete.
    """
    try:
        abs_path = resolve_file_path(file_path)
    except FileNotFoundError:
        return

    os.remove(abs_path)
