from fastapi import HTTPException, UploadFile

IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
DOCUMENT_TYPES = {**IMAGE_TYPES, "application/pdf": ".pdf"}

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024   # 5 MB
MAX_DOCUMENT_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


async def read_validated_upload(file: UploadFile, allowed_types: dict, max_size_bytes: int) -> tuple[bytes, str]:
    """
    Reads an UploadFile after validating its declared content-type against an
    allowlist and its size against a limit. Returns (bytes, extension) where
    the extension is derived from the validated content-type, never from the
    client-supplied filename (avoids trusting attacker-controlled names/paths).
    """
    if file.content_type not in allowed_types:
        allowed = ", ".join(sorted(set(allowed_types.values())))
        raise HTTPException(status_code=400, detail=f"Tipo de archivo no permitido. Formatos aceptados: {allowed}")

    contents = await file.read()
    if len(contents) > max_size_bytes:
        raise HTTPException(status_code=400, detail=f"El archivo supera el tamaño máximo permitido ({max_size_bytes // (1024*1024)} MB)")

    return contents, allowed_types[file.content_type]
