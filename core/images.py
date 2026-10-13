"""Validation and resizing for uploaded images (profile photos, logos)."""

from io import BytesIO
from pathlib import PurePosixPath

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
RESIZE_SIZES = (512, 128)  # longest side, in pixels
_INVALID_MESSAGE = "Upload a valid JPEG, PNG, or WebP image."


def _pixel_limit(image: Image.Image) -> int:
    # JPEGs decode at reduced scale (draft), so they can be larger than PNG/WebP.
    if image.format == "JPEG":
        return settings.IMAGE_MAX_PIXELS_JPEG
    return settings.IMAGE_MAX_PIXELS


def _too_many_pixels(image: Image.Image) -> bool:
    # A tiny, highly compressed file can decode to gigabytes (decompression bomb).
    return image.width * image.height > _pixel_limit(image)


def validate_image_upload(file) -> None:
    if getattr(file, "_committed", False):
        # Already in storage: it was validated on upload, and the file may not even be on disk
        # (e.g. a database restored without media).
        return
    max_bytes = settings.IMAGE_UPLOAD_MAX_BYTES
    if file.size > max_bytes:
        raise ValidationError(
            "Images must be %(limit)s MB or smaller.",
            code="too_large",
            params={"limit": max_bytes // (1024 * 1024) or 1},
        )
    try:
        file.seek(0)
        with Image.open(file) as image:
            image_format = image.format
            too_many_pixels = _too_many_pixels(image)
            pixel_limit = _pixel_limit(image)
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValidationError(_INVALID_MESSAGE, code="invalid_image") from exc
    finally:
        file.seek(0)
    if image_format not in ALLOWED_FORMATS:
        raise ValidationError(_INVALID_MESSAGE, code="invalid_format")
    if too_many_pixels:
        raise ValidationError(
            "Images must be %(limit)s megapixels or smaller.",
            code="too_many_pixels",
            params={"limit": pixel_limit // 1_000_000 or 1},
        )


def variant_name(name: str, size: int) -> str:
    path = PurePosixPath(name)
    return str(path.with_name(f"{path.stem}.{size}.webp"))


def _normalize_mode(image: Image.Image) -> Image.Image:
    if image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info:
        return image.convert("RGBA")
    return image.convert("RGB")


def create_variants(name: str, sizes=RESIZE_SIZES) -> list[str]:
    """Write WebP copies of stored image `name`, each fitting within size x size."""
    created = []
    largest = max(sizes)
    with default_storage.open(name, "rb") as source, Image.open(source) as original:
        if _too_many_pixels(original):
            raise ValueError(f"{name} has too many pixels to resize.")
        # Keep peak memory low: JPEGs decode at a reduced scale, and everything is shrunk to the
        # largest variant before rotating.
        original.draft("RGB", (largest * 2, largest * 2))
        image = _normalize_mode(original)
        image.thumbnail((largest, largest), Image.Resampling.LANCZOS)
        image = ImageOps.exif_transpose(image)
        for size in sorted(sizes, reverse=True):
            variant = image.copy()
            variant.thumbnail((size, size), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            variant.save(buffer, format="WEBP", quality=82)
            target = variant_name(name, size)
            if default_storage.exists(target):
                default_storage.delete(target)
            created.append(default_storage.save(target, ContentFile(buffer.getvalue())))
    return created


def variant_url(field_file, size: int) -> str:
    """URL of the resized variant if it exists yet, otherwise of the original."""
    if not field_file:
        return ""
    name = variant_name(field_file.name, size)
    if default_storage.exists(name):
        return default_storage.url(name)
    return field_file.url


def delete_image(name: str, sizes=RESIZE_SIZES) -> None:
    """Delete a stored image and its resized variants, skipping files that are already gone."""
    for path in (name, *(variant_name(name, size) for size in sizes)):
        if default_storage.exists(path):
            default_storage.delete(path)
