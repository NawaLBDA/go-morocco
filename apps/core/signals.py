from django.db.models.signals import pre_save, post_save, m2m_changed
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from .models import Reservation, Tour, Guide


@receiver(post_save, sender=Reservation)
def booking_created(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    from apps.reservations.notifications import queue_booking_notifications
    previous = getattr(instance, '_notification_previous', None) or {}
    fields = kwargs.get('update_fields')
    if created:
        queue_booking_notifications(instance, event='requested')
    if instance.status == 'booked' and (created or previous.get('status') != 'booked') and (fields is None or 'status' in fields):
        queue_booking_notifications(instance, event='approved')
    if instance.payment_status == 'paid' and (created or previous.get('payment_status') != 'paid') and (fields is None or 'payment_status' in fields):
        queue_booking_notifications(instance, event='paid')
    if not created and instance.status in {'rejected', 'cancelled', 'completed'} and previous.get('status') != instance.status and (fields is None or 'status' in fields):
        queue_booking_notifications(instance, event=instance.status)


@receiver(pre_save, sender=Reservation)
def remember_booking_state(sender, instance, raw=False, **kwargs):
    if not raw:
        instance._notification_previous = Reservation.objects.filter(pk=instance.pk).values('status', 'payment_status').first() if instance.pk else None


@receiver(m2m_changed, sender=Tour.guides.through)
def validate_guide_country(sender, instance, action, reverse, pk_set, **kwargs):
    if action != 'pre_add' or not pk_set:
        return
    if reverse:
        invalid = Tour.objects.filter(pk__in=pk_set).exclude(country=instance.country_id).exists()
    else:
        invalid = Guide.objects.filter(pk__in=pk_set).exclude(country_id=instance.country).exists()
    if invalid:
        raise ValidationError('A guiding team must belong to the same country as its tour.')


@receiver(m2m_changed, sender=Reservation.assigned_guides.through)
def validate_assigned_guide(sender, instance, action, reverse, pk_set, **kwargs):
    if action != 'pre_add' or not pk_set:
        return
    from apps.reservations.availability import ACTIVE_STATUSES, lock_guide_calendar
    bookings = list(Reservation.objects.filter(pk__in=pk_set).select_related('tour')) if reverse else [instance]
    guide_ids = [instance.pk] if reverse else pk_set
    if reverse:
        active = [b for b in bookings if b.status in ACTIVE_STATUSES]
        for i, booking in enumerate(active):
            if any(other.start_date <= booking.end_date and other.end_date >= booking.start_date for other in active[i + 1:]):
                raise ValidationError('A guide cannot be assigned to overlapping groups.')
    for booking in bookings:
        with lock_guide_calendar(booking.tour.country):
            if Guide.objects.filter(pk__in=guide_ids).exclude(country_id=booking.tour.country).exists():
                raise ValidationError('Assign guides from the same country as the booking.')
            if booking.status in ACTIVE_STATUSES and Reservation.objects.filter(
                    assigned_guides__pk__in=guide_ids, status__in=ACTIVE_STATUSES,
                    start_date__lte=booking.end_date, end_date__gte=booking.start_date).exclude(pk=booking.pk).exists():
                raise ValidationError('This guide is already assigned to another active group on these dates.')
