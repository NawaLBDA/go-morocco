from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Reservation


@receiver(post_save, sender=Reservation)
def booking_created(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        from apps.reservations.notifications import queue_booking_notifications
        queue_booking_notifications(instance)
