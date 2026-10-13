import pytest
from django.db import connection


@pytest.mark.django_db
def test_database_is_postgres():
    assert connection.vendor == "postgresql"
