from datetime import timedelta
from io import BytesIO

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image

from core.celery import app as celery_app
from tests.constants import PASSWORD


@pytest.fixture(autouse=True)
def _celery_eager():
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture(autouse=True)
def _fast_password_hashing(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def make_image_file():
    def make(name="photo.png", fmt="PNG", size=(800, 600), mode="RGB", orientation=None):
        image = Image.new(mode, size)
        buffer = BytesIO()
        save_kwargs = {}
        if orientation is not None:
            exif = Image.Exif()
            exif[0x0112] = orientation
            save_kwargs["exif"] = exif
        if mode == "P":
            save_kwargs["transparency"] = 0
        image.save(buffer, format=fmt, **save_kwargs)
        return SimpleUploadedFile(name, buffer.getvalue(), content_type=f"image/{fmt.lower()}")

    return make


@pytest.fixture
def make_user(django_user_model):
    def make(email="volunteer@example.org", **extra):
        return django_user_model.objects.create_user(
            username=email, email=email, password=PASSWORD, **extra
        )

    return make


@pytest.fixture
def complete_user(make_user, django_user_model):
    def make(email="volunteer@example.org"):
        from accounts.models import Profile

        user = make_user(email)
        Profile.objects.filter(user=user).update(
            first_name="Ada", last_name="Lovelace", phone="617-555-0100"
        )
        return django_user_model.objects.get(pk=user.pk)

    return make


@pytest.fixture
def location(db):
    from events.models import Location

    return Location.objects.create(
        name="Community Center",
        address_line1="12 Main St",
        city="Boston",
        region="MA",
        postal_code="02118",
        country="USA",
    )


@pytest.fixture
def make_event(location):
    from events.models import Event, Position

    def make(title="Food drive", status="published", positions=((24, 3),), **extra):
        extra.setdefault("location", location)
        event = Event.objects.create(title=title, status=status, **extra)
        now = timezone.now()
        for index, (offset_hours, duration_hours) in enumerate(positions, start=1):
            starts_at = now + timedelta(hours=offset_hours)
            Position.objects.create(
                event=event,
                title=f"Shift {index}",
                starts_at=starts_at,
                ends_at=starts_at + timedelta(hours=duration_hours),
                slots=5,
            )
        return event

    return make


@pytest.fixture
def coordinator(complete_user):
    from organization.roles import Role, set_role

    user = complete_user("coordinator@example.org")
    set_role(user, Role.COORDINATOR)
    return user


@pytest.fixture
def org_admin(complete_user):
    from organization.roles import Role, set_role

    user = complete_user("admin@example.org")
    set_role(user, Role.ADMIN)
    return user


@pytest.fixture
def make_position(make_event):
    from events.models import Position

    def make(slots=2, starts_in_hours=48, hours=3, event=None, status="published", title="Shift"):
        if event is None:
            event = make_event(title=f"Event for {title}", status=status, positions=())
        starts_at = timezone.now() + timedelta(hours=starts_in_hours)
        return Position.objects.create(
            event=event,
            title=title,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=hours),
            slots=slots,
        )

    return make


@pytest.fixture
def make_volunteer(complete_user):
    def make(n=1):
        return complete_user(f"vol{n}@example.org")

    return make


@pytest.fixture
def volunteer(make_volunteer):
    return make_volunteer(1)


@pytest.fixture
def backup_tools(tmp_path, monkeypatch, settings):
    from tests.backup_stubs import BackupTools

    return BackupTools(tmp_path, monkeypatch, settings)
