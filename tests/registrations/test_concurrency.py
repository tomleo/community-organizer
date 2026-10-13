import threading

import pytest
from django.db import connection

from registrations import services
from registrations.models import Registration


@pytest.mark.django_db(transaction=True)
def test_two_volunteers_racing_for_the_last_spot(make_volunteer, make_position):
    position = make_position(slots=1)
    volunteers = [make_volunteer(1), make_volunteer(2)]
    barrier = threading.Barrier(len(volunteers))
    errors = []

    def attempt(volunteer):
        try:
            barrier.wait()
            services.register(volunteer, position)
        except Exception as exc:  # surfaced below
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt, args=(volunteer,)) for volunteer in volunteers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert sorted(Registration.objects.values_list("status", flat=True)) == [
        "registered",
        "waitlisted",
    ]
