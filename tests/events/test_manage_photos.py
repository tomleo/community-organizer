import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from core.images import variant_name
from events.models import EVENT_PHOTO_LIMIT, EventPhoto

pytestmark = pytest.mark.django_db


def upload(client, event, files):
    return client.post(
        reverse("manage_photos_upload", args=[event.pk]), {"photos": files}, follow=True
    )


def test_multi_upload_creates_ordered_photos_and_variants(
    client, coordinator, make_event, make_image_file, django_capture_on_commit_callbacks
):
    event = make_event()
    client.force_login(coordinator)
    with django_capture_on_commit_callbacks(execute=True):
        response = upload(
            client, event, [make_image_file(name="a.png"), make_image_file(name="b.png")]
        )
    assert "Added 2 photos." in response.content.decode()
    photos = list(event.photos.all())
    assert [photo.position for photo in photos] == [0, 1]
    assert default_storage.exists(variant_name(photos[0].image.name, 1600))
    assert default_storage.exists(variant_name(photos[0].image.name, 800))


def test_upload_rejects_non_images(client, coordinator, make_event):
    event = make_event()
    client.force_login(coordinator)
    response = upload(
        client, event, [SimpleUploadedFile("x.jpg", b"nope", content_type="image/jpeg")]
    )
    assert "valid" in response.content.decode().lower()
    assert not event.photos.exists()


def test_photo_limit(client, coordinator, make_event, make_image_file):
    event = make_event()
    for index in range(EVENT_PHOTO_LIMIT - 1):
        EventPhoto.objects.create(event=event, image=make_image_file(), position=index)
    client.force_login(coordinator)
    response = upload(client, event, [make_image_file(), make_image_file()])
    assert "You can add 1 more photo" in response.content.decode()
    assert event.photos.count() == EVENT_PHOTO_LIMIT - 1


def test_move_photos(client, coordinator, make_event, make_image_file):
    event = make_event()
    first = EventPhoto.objects.create(event=event, image=make_image_file(), position=0)
    second = EventPhoto.objects.create(event=event, image=make_image_file(), position=1)
    client.force_login(coordinator)
    client.post(reverse("manage_photo_move", args=[second.pk, "up"]))
    assert list(event.photos.all()) == [second, first]
    client.post(reverse("manage_photo_move", args=[second.pk, "down"]))
    assert list(event.photos.all()) == [first, second]
    client.post(reverse("manage_photo_move", args=[first.pk, "up"]))  # already first: no change
    assert list(event.photos.all()) == [first, second]


def test_delete_photo_removes_files(
    client, coordinator, make_event, make_image_file, django_capture_on_commit_callbacks
):
    from core.images import create_variants

    event = make_event()
    photo = EventPhoto.objects.create(event=event, image=make_image_file(), position=0)
    name = photo.image.name
    create_variants(name, (1600, 800))
    client.force_login(coordinator)
    with django_capture_on_commit_callbacks(execute=True):
        client.post(reverse("manage_photo_delete", args=[photo.pk]))
    assert not EventPhoto.objects.filter(pk=photo.pk).exists()
    assert not default_storage.exists(name)
    assert not default_storage.exists(variant_name(name, 1600))


def test_photo_views_forbidden_for_volunteers(client, complete_user, make_event, make_image_file):
    event = make_event()
    photo = EventPhoto.objects.create(event=event, image=make_image_file(), position=0)
    client.force_login(complete_user())
    assert client.post(reverse("manage_photos_upload", args=[event.pk])).status_code == 403
    assert client.post(reverse("manage_photo_move", args=[photo.pk, "up"])).status_code == 403
    assert client.post(reverse("manage_photo_delete", args=[photo.pk])).status_code == 403


def test_hub_shows_photo_controls(client, coordinator, make_event, make_image_file):
    event = make_event()
    photo = EventPhoto.objects.create(event=event, image=make_image_file(), position=0)
    client.force_login(coordinator)
    content = client.get(reverse("manage_event", args=[event.pk])).content.decode()
    assert reverse("manage_photos_upload", args=[event.pk]) in content
    assert reverse("manage_photo_delete", args=[photo.pk]) in content
    assert 'enctype="multipart/form-data"' in content
