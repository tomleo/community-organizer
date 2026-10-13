import pytest
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from core.images import create_variants, validate_image_upload, variant_name, variant_url


def test_validate_accepts_supported_formats(make_image_file):
    for fmt in ("PNG", "JPEG", "WEBP"):
        validate_image_upload(make_image_file(name=f"x.{fmt.lower()}", fmt=fmt))


def test_validate_rejects_oversized(settings, make_image_file):
    settings.IMAGE_UPLOAD_MAX_BYTES = 100
    with pytest.raises(ValidationError) as excinfo:
        validate_image_upload(make_image_file())
    assert excinfo.value.code == "too_large"


def test_validate_rejects_non_image():
    fake = SimpleUploadedFile("photo.jpg", b"definitely not an image", content_type="image/jpeg")
    with pytest.raises(ValidationError) as excinfo:
        validate_image_upload(fake)
    assert excinfo.value.code == "invalid_image"


def test_validate_rejects_gif(make_image_file):
    with pytest.raises(ValidationError) as excinfo:
        validate_image_upload(make_image_file(name="x.gif", fmt="GIF"))
    assert excinfo.value.code == "invalid_format"


def test_variant_name():
    assert variant_name("profiles/a.png", 512) == "profiles/a.512.webp"


def _store(upload):
    return default_storage.save(f"uploads/{upload.name}", upload)


def test_create_variants_scales_longest_side(make_image_file):
    name = _store(make_image_file(size=(800, 600)))

    created = create_variants(name)

    assert created == [variant_name(name, 512), variant_name(name, 128)]
    with default_storage.open(created[0]) as f, Image.open(f) as image:
        assert image.format == "WEBP"
        assert image.size == (512, 384)
    with default_storage.open(created[1]) as f, Image.open(f) as image:
        assert image.size == (128, 96)
    assert default_storage.exists(name)  # original kept


def test_create_variants_applies_exif_orientation(make_image_file):
    # Orientation 6 = camera rotated 90°; a landscape-encoded JPEG displays as portrait.
    name = _store(make_image_file(name="phone.jpg", fmt="JPEG", size=(800, 400), orientation=6))

    create_variants(name)

    with default_storage.open(variant_name(name, 512)) as f, Image.open(f) as image:
        assert image.size == (256, 512)


@pytest.mark.parametrize(("fmt", "mode"), [("PNG", "P"), ("JPEG", "CMYK"), ("PNG", "LA")])
def test_create_variants_handles_unusual_modes(make_image_file, fmt, mode):
    name = _store(make_image_file(name=f"odd.{fmt.lower()}", fmt=fmt, mode=mode))

    assert len(create_variants(name)) == 2


def test_create_variants_does_not_upscale(make_image_file):
    name = _store(make_image_file(size=(100, 50)))
    create_variants(name)
    with default_storage.open(variant_name(name, 512)) as f, Image.open(f) as image:
        assert image.size == (100, 50)


def test_variant_url_falls_back_to_original(make_image_file):
    from django.db.models.fields.files import FieldFile

    class Holder:
        pass

    name = _store(make_image_file())
    field_file = FieldFile(Holder(), type("F", (), {"storage": default_storage})(), name)

    assert variant_url(field_file, 512) == default_storage.url(name)
    create_variants(name)
    assert variant_url(field_file, 512) == default_storage.url(variant_name(name, 512))


def test_variant_url_empty_file():
    assert variant_url(None, 512) == ""


def test_validate_rejects_too_many_pixels(settings, make_image_file):
    # A small file can still decode to a huge bitmap (decompression bomb).
    settings.IMAGE_MAX_PIXELS = 100 * 100
    with pytest.raises(ValidationError) as excinfo:
        validate_image_upload(make_image_file(size=(101, 100)))
    assert excinfo.value.code == "too_many_pixels"


def test_create_variants_refuses_too_many_pixels(settings, make_image_file):
    name = _store(make_image_file(size=(400, 300)))
    settings.IMAGE_MAX_PIXELS = 1000

    with pytest.raises(ValueError, match="too many pixels"):
        create_variants(name)
    assert not default_storage.exists(variant_name(name, 512))


def test_jpeg_has_its_own_higher_pixel_limit(settings, make_image_file):
    # JPEGs decode at reduced scale, so large phone photos stay cheap to resize.
    settings.IMAGE_MAX_PIXELS = 100
    settings.IMAGE_MAX_PIXELS_JPEG = 1_000_000
    upload = make_image_file(name="phone.jpg", fmt="JPEG", size=(400, 300))

    validate_image_upload(upload)
    assert len(create_variants(_store(upload))) == 2


def test_validate_skips_already_stored_files(make_image_file):
    from django.db.models.fields.files import FieldFile

    class Holder:
        pass

    stored = FieldFile(Holder(), type("F", (), {"storage": default_storage})(), "missing/x.png")
    validate_image_upload(stored)  # existing files were validated when uploaded


def test_delete_image_removes_original_and_variants(make_image_file):
    from core.images import delete_image

    name = _store(make_image_file())
    create_variants(name, sizes=(1600, 800))

    delete_image(name, sizes=(1600, 800))

    assert not default_storage.exists(name)
    assert not default_storage.exists(variant_name(name, 1600))
    assert not default_storage.exists(variant_name(name, 800))


def test_delete_image_tolerates_missing_files():
    from core.images import delete_image

    delete_image("missing/none.png", sizes=(1600, 800))
