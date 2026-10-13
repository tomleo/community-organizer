from celery import shared_task

from registrations import services


@shared_task
def expire_offers():
    return services.expire_offers()
