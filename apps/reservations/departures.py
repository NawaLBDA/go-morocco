from apps.core.countries import uses_scheduled_departures
"""Published, administrator-planned Morocco departures."""
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db.models import Q

from apps.core.models import TourDeparture
from .availability import has_conflict, departure_capacity


def available_departure_ranges(*, anchor=None, limit=4, country='morocco'):
    """Chat suggestions must use published departures, never invented windows."""
    anchor = anchor or date.today()
    departures = list(TourDeparture.objects.filter(tour__country=country,
        is_published=True, start_date__gte=date.today()).select_related('tour'))
    departures.sort(key=lambda departure: (abs((departure.start_date - anchor).days), departure.start_date))
    ranges = []
    for departure in departures:
        period = (departure.start_date, departure.end_date)
        if (period not in ranges and departure.duration_days <= departure.tour.max_days
                and departure.active_days and not has_conflict(*period, country=country, departure=departure)):
            ranges.append(period)
            if len(ranges) >= limit:
                break
    return ranges


def resolve_departure(tour, start, end, departure_id=None):
    departures = TourDeparture.objects.filter(tour=tour, is_published=True)
    if departure_id:
        try:
            departures = departures.filter(pk=int(departure_id))
        except (ValueError, TypeError):
            raise ValidationError('Choose one of the published departures for this tour.')
    departure = departures.filter(start_date=start, end_date=end).first()
    if not departure or departure.start_date < date.today():
        raise ValidationError('Choose one of the published departures for this tour.')
    if departure.duration_days > tour.max_days or not departure.active_days:
        raise ValidationError('This departure is not currently available. Please choose another departure.')
    return departure


def departure_context(request, tour, reservation=None):
    if not uses_scheduled_departures(tour.country):
        return {}
    requested = request.GET.get('departure_id', '')
    selection = Q(start_date__gte=date.today())
    if requested.isdigit():
        selection |= Q(pk=int(requested))
    departures = list(tour.departures.filter(selection, is_published=True).prefetch_related('program_days'))
    options = []
    selected = None
    requested = request.GET.get('departure_id', '')
    for departure in departures:
        count = sum(day.is_visible for day in departure.program_days.all())
        if not count or departure.duration_days > tour.max_days:
            continue
        departure.billable_days = count
        capacity = departure_capacity(departure)
        departure.is_past = departure.start_date < date.today()
        departure.available = capacity['available'] and not departure.is_past
        departure.booked_groups = capacity['booked_groups']
        departure.booked_travelers = capacity['booked_travelers']
        options.append(departure)
        if str(departure.pk) == requested or (not requested and
            request.GET.get('start_date') == departure.start_date.isoformat() and
            request.GET.get('end_date') == departure.end_date.isoformat()):
            selected = departure
    if reservation and reservation.departure_id:
        selected = reservation.departure
    if requested and not selected:
        from django.http import Http404
        raise Http404('This departure is not available for this journey.')
    if selected:
        capacity = departure_capacity(selected)
        selected.is_past = selected.start_date < date.today()
        selected.available = capacity['available'] and not selected.is_past
        selected.booked_groups = capacity['booked_groups']
        selected.booked_travelers = capacity['booked_travelers']
    included_days = []
    if selected:
        included_days = [{'number': day.day_number,
                          'date': selected.start_date + timedelta(days=day.day_number - 1),
                          'title': day.title}
                         for day in selected.program_days.filter(is_visible=True)]
    from apps.core.models import WaitlistEntry
    waitlist = WaitlistEntry.objects.filter(user=request.user, departure=selected).first() if request.user.is_authenticated and selected else None
    return {'waitlist_entry': waitlist, 'tour_departures': options, 'selected_departure': selected,
            'departure_included_days': included_days}
