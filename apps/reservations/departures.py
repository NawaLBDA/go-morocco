"""Published, administrator-planned Morocco departures."""
from datetime import date, timedelta

from django.core.exceptions import ValidationError

from apps.core.models import TourDeparture
from .availability import has_conflict


def available_departure_ranges(*, anchor=None, limit=4):
    """Chat suggestions must use published departures, never invented windows."""
    anchor = anchor or date.today()
    departures = list(TourDeparture.objects.filter(tour__country='morocco',
        is_published=True, start_date__gte=date.today()).select_related('tour'))
    departures.sort(key=lambda departure: (abs((departure.start_date - anchor).days), departure.start_date))
    ranges = []
    for departure in departures:
        period = (departure.start_date, departure.end_date)
        if (period not in ranges and departure.duration_days <= departure.tour.max_days
                and departure.active_days and not has_conflict(*period)):
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
    if tour.country != 'morocco':
        return {}
    departures = list(tour.departures.filter(is_published=True, start_date__gte=date.today()).prefetch_related('program_days'))
    options = []
    selected = None
    requested = request.GET.get('departure_id', '')
    for departure in departures:
        count = sum(day.is_visible for day in departure.program_days.all())
        if not count or departure.duration_days > tour.max_days:
            continue
        departure.billable_days = count
        departure.available = not has_conflict(departure.start_date, departure.end_date)
        options.append(departure)
        if str(departure.pk) == requested or (not requested and
            request.GET.get('start_date') == departure.start_date.isoformat() and
            request.GET.get('end_date') == departure.end_date.isoformat()):
            selected = departure
    if reservation and reservation.departure_id:
        selected = reservation.departure
    included_days = []
    if selected:
        included_days = [{'number': day.day_number,
                          'date': selected.start_date + timedelta(days=day.day_number - 1),
                          'title': day.title}
                         for day in selected.program_days.filter(is_visible=True)]
    return {'tour_departures': options, 'selected_departure': selected,
            'departure_included_days': included_days}
