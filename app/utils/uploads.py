from fastapi import HTTPException, UploadFile

IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
DOCUMENT_TYPES = {
    **IMAGE_TYPES,
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}
DOCUMENT_RULES = "PDF, Word, JPG, PNG o WebP de hasta 10 MB"

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


# --- Photos from phones ---------------------------------------------------------------
# Phones take 3-8 MB photos and iPhones may send HEIC. Every photo is accepted up to
# MAX_PHOTO_UPLOAD_BYTES, turned upright (EXIF), resized to PHOTO_MAX_SIDE px and saved as
# JPEG, so reports, e-mails and storage stay light.
PHOTO_TYPES = {**IMAGE_TYPES, "image/heic": ".heic", "image/heif": ".heif", "image/heic-sequence": ".heic"}
PHOTO_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif")
MAX_PHOTO_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB before resizing
PHOTO_MAX_SIDE = 2048
PHOTO_QUALITY = 82
PHOTO_RULES = "Fotos JPEG, PNG, WebP o HEIC (iPhone) de hasta 20 MB"


def is_photo(content_type: str, filename: str) -> bool:
    return content_type in PHOTO_TYPES or (filename or "").lower().endswith(PHOTO_EXTENSIONS)


def process_photo(contents: bytes, content_type: str, filename: str) -> bytes:
    """Validated, upright, resized JPEG bytes. Raises HTTPException(400) naming the file."""
    from io import BytesIO

    from PIL import Image, ImageOps, UnidentifiedImageError
    import pillow_heif

    pillow_heif.register_heif_opener()
    name = filename or "la foto"
    if not is_photo(content_type, filename):
        raise HTTPException(status_code=400, detail=f"«{name}» no es una foto. {PHOTO_RULES}.")
    if len(contents) > MAX_PHOTO_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail=f"«{name}» pesa más de 20 MB.")
    try:
        with Image.open(BytesIO(contents)) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in ("RGB", "L"):
                background = Image.new("RGB", image.size, (255, 255, 255))
                if "A" in image.getbands():
                    background.paste(image, mask=image.getchannel("A"))
                else:
                    background.paste(image.convert("RGB"))
                image = background
            image.thumbnail((PHOTO_MAX_SIDE, PHOTO_MAX_SIDE))
            out = BytesIO()
            image.convert("RGB").save(out, "JPEG", quality=PHOTO_QUALITY, optimize=True)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(status_code=400, detail=f"No se pudo leer «{name}» como foto. {PHOTO_RULES}.")
