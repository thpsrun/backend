import io

from PIL import Image

# These are magic byte prefixes for JPEG, PNG, and the GIFs. These are what are allowed by the
# backend, since anything other than this could be malicious. This is just one of the few guards the
# site takes to prevent potential threats from occurring.
_MAGIC_PREFIXES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "JPEG"),
    (b"\x89PNG\r\n\x1a\n", "PNG"),
    (b"GIF87a", "GIF"),
    (b"GIF89a", "GIF"),
)
_WEBP_RIFF: bytes = b"RIFF"
_WEBP_MARKER: bytes = b"WEBP"
_ALLOWED_FORMATS: frozenset[str] = frozenset({"JPEG", "PNG", "GIF", "WEBP"})
_REJECTED_MIMES: frozenset[str] = frozenset({"image/svg+xml", "image/svg"})


class ImageValidationError(Exception):
    """Raised when an uploaded image fails any validation check (e.g. magic byte)."""

    def __init__(
        self,
        message: str,
    ) -> None:
        self.message: str = message
        super().__init__(message)


def _detect_format(
    raw: bytes,
) -> str | None:
    for prefix, fmt in _MAGIC_PREFIXES:
        if raw.startswith(prefix):
            return fmt
    if raw.startswith(_WEBP_RIFF) and len(raw) >= 12 and raw[8:12] == _WEBP_MARKER:
        return "WEBP"
    return None


def validate_image(
    raw: bytes,
    mime: str | None,
    max_pixels: int,
) -> Image.Image:
    """Validate and decode an uploaded image, returning an RGB copy.

    Arguments:
        raw (bytes): Raw file bytes from the upload.
        mime (str | None): Client-supplied MIME; used only to reject SVG.
        max_pixels (int): Maximum allowed pixel count (width * height).

    Returns:
        Image.Image: RGB-converted PIL image ready for re-encoding. For
        animated formats (GIF) the first frame is used.

    Raises:
        ImageValidationError: On any failed validation gate, with a message
        safe to return to the client.
    """
    if mime:
        main_type: str = mime.split(";", 1)[0].strip().lower()
        if main_type in _REJECTED_MIMES:
            raise ImageValidationError("SVG images are not supported")

    detected: str | None = _detect_format(raw)
    if detected is None:
        raise ImageValidationError("Unsupported image format")

    try:
        with Image.open(io.BytesIO(raw)) as probe:
            probe.verify()
    except Exception as e:
        raise ImageValidationError("Uploaded file is not a valid image") from e

    try:
        with Image.open(io.BytesIO(raw)) as img:
            if img.format not in _ALLOWED_FORMATS or img.format != detected:
                raise ImageValidationError("Unsupported image format")
            if img.width * img.height > max_pixels:
                raise ImageValidationError(
                    "Image dimensions exceed the allowed maximum"
                )
            return img.convert("RGB")
    except ImageValidationError:
        raise
    except Exception as e:
        raise ImageValidationError("Uploaded file is not a valid image") from e
