"""The Morocco guide has one shared calendar across every tour and traveler."""
from contextlib import contextmanager

from django.core.exceptions import ValidationError
from django.db import transaction

ACTIVE_STATUSES = ('pending', 'booked')
UNAVAILABLE_MESSAGE = (
    'Your guide is unavailable for part of these dates. Only one traveler or private '
    'group can be guided at a time across all Morocco tours. Please choose other dates.'
)


def active_reservations():
    from apps.core.models import Reservation
    return Reservation.objects.filter(tour__country='morocco', status__in=ACTIVE_STATUSES)


def has_conflict(start, end, *, exclude_id=None):
    return active_reservations().exclude(pk=exclude_id).filter(
        start_date__lte=end, end_date__gte=start,
    ).exists()


def validate_reservation(reservation):
    if not reservation.tour_id or reservation.tour.country != 'morocco':
        return
    if not reservation.start_date or not reservation.end_date:
        return
    if reservation.end_date <= reservation.start_date:
        raise ValidationError('End date must be after start date.')
    if reservation.status in ACTIVE_STATUSES and has_conflict(
        reservation.start_date, reservation.end_date, exclude_id=reservation.pk,
    ):
        raise ValidationError(UNAVAILABLE_MESSAGE)


@contextmanager
def lock_guide_calendar():
    # A stable row serializes bookings even when the calendar is completely empty.
    # Locking just matching reservations would leave that case unprotected.
    from apps.core.models import GuideCalendar
    with transaction.atomic():
        GuideCalendar.objects.get_or_create(country='morocco')
        GuideCalendar.objects.select_for_update().get(country='morocco')
        yield
