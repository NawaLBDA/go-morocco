"""Capacity checks for private groups; all writes use the stable country lock."""
from collections import defaultdict
from contextlib import contextmanager
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.db import transaction
from apps.core.countries import uses_scheduled_departures

ACTIVE_STATUSES = ('pending', 'booked')
UNAVAILABLE_MESSAGE = 'The guiding team or this departure is fully reserved for these dates. You can join the waiting list for a review.'


def active_reservations(country='morocco'):
    from apps.core.models import Reservation
    return Reservation.objects.filter(tour__country=country, status__in=ACTIVE_STATUSES)


def full_calendar_ranges(country='morocco'):
    """Inclusive intervals where the entire country team is at capacity."""
    from datetime import date
    from apps.core.models import Country
    events = defaultdict(int)
    for start, end in active_reservations(country).values_list('start_date', 'end_date'):
        events[start] += 1
        if end < date.max:
            events[end + timedelta(days=1)] -= 1
    limit = Country.objects.get(slug=country).max_concurrent_groups
    count, opened, ranges = 0, None, []
    for day in sorted(events):
        count += events[day]
        if count >= limit and opened is None:
            opened = day
        elif count < limit and opened is not None:
            ranges.append((opened, day - timedelta(days=1)))
            opened = None
    if opened is not None:
        ranges.append((opened, date.max))
    return ranges


def peak_groups(rows, start, end):
    events = defaultdict(int)
    for row in rows:
        first, last = max(start, row['start_date']), min(end, row['end_date'])
        if first <= last:
            events[first] += 1
            if last < end:
                events[last + timedelta(days=1)] -= 1
    count = peak = 0
    for day in sorted(events):
        count += events[day]
        peak = max(peak, count)
    return peak


def has_conflict(start, end, *, exclude_id=None, country='morocco', departure=None, rows=None, country_limit=None):
    from apps.core.models import Country
    if rows is None:
        rows = list(active_reservations(country).exclude(pk=exclude_id).filter(
            start_date__lte=end, end_date__gte=start).values('id', 'start_date', 'end_date', 'departure_id', 'num_persons'))
    else:
        rows = [r for r in rows if r['id'] != exclude_id and r['start_date'] <= end and r['end_date'] >= start]
    limit = country_limit if country_limit is not None else Country.objects.get(slug=country).max_concurrent_groups
    if peak_groups(rows, start, end) >= limit:
        return True
    return bool(departure and sum(r['departure_id'] == departure.pk for r in rows) >= departure.max_concurrent_bookings)


def departure_capacity(departure, *, rows=None, country_limit=None, exclude_id=None):
    if rows is None:
        rows = list(active_reservations(departure.tour.country).values(
            'id', 'start_date', 'end_date', 'departure_id', 'num_persons'))
    exact = [r for r in rows if r['departure_id'] == departure.pk and r['id'] != exclude_id]
    from django.utils import timezone
    if departure.start_date < timezone.localdate():
        from apps.core.models import Reservation
        exact = list(Reservation.objects.filter(departure=departure,
            status__in=['pending', 'booked', 'completed']).exclude(pk=exclude_id).values('num_persons'))
    if country_limit is None:
        country_limit = departure.tour.region.max_concurrent_groups
    available = not has_conflict(departure.start_date, departure.end_date,
        country=departure.tour.country, departure=departure, rows=rows,
        country_limit=country_limit, exclude_id=exclude_id)
    return {'available': available, 'booked_groups': len(exact),
        'booked_travelers': sum(r['num_persons'] for r in exact),
        'max_participants': departure.max_participants,
        'max_groups': min(departure.max_concurrent_bookings, country_limit)}


def validate_reservation(reservation):
    if not reservation.pk and reservation.num_persons > 20:
        raise ValidationError("Groups are limited to 20 travelers.")
    if reservation.departure_id and not 1 <= reservation.num_persons <= reservation.departure.max_participants:
        raise ValidationError('Choose a group size between 1 and the departure maximum.')
    if not reservation.tour_id or not uses_scheduled_departures(reservation.tour.country):
        return
    if not reservation.start_date or not reservation.end_date:
        return
    if reservation.end_date < reservation.start_date:
        raise ValidationError('End date cannot be before start date.')
    if reservation.departure_id:
        departure = reservation.departure
        if (departure.tour_id != reservation.tour_id or departure.start_date != reservation.start_date
                or departure.end_date != reservation.end_date):
            raise ValidationError('Reservation dates and tour must match the selected departure.')
    if reservation.status in ACTIVE_STATUSES:
        if reservation.departure_id:
            from apps.core.models import Reservation
            if Reservation.objects.filter(user_id=reservation.user_id, departure_id=reservation.departure_id,
                    status__in=ACTIVE_STATUSES).exclude(pk=reservation.pk).exists():
                raise ValidationError('This traveler already has an active booking for this departure.')
        if has_conflict(reservation.start_date, reservation.end_date, exclude_id=reservation.pk,
                country=reservation.tour.country, departure=reservation.departure):
            raise ValidationError(UNAVAILABLE_MESSAGE)
        if reservation.pk:
            guides = reservation.assigned_guides.all()
            if guides.exclude(country_id=reservation.tour.country).exists():
                raise ValidationError('Assigned guides must belong to this country.')
            from apps.core.models import Reservation
            if Reservation.objects.filter(assigned_guides__in=guides, status__in=ACTIVE_STATUSES,
                    start_date__lte=reservation.end_date, end_date__gte=reservation.start_date).exclude(pk=reservation.pk).exists():
                raise ValidationError('An assigned guide is already guiding another group on these dates.')



@contextmanager
def lock_guide_calendar(country='morocco'):
    from apps.core.models import GuideCalendar
    with transaction.atomic():
        GuideCalendar.objects.get_or_create(country=country)
        GuideCalendar.objects.select_for_update().get(country=country)
        yield
