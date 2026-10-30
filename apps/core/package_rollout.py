"""One-time two-week package rollout; existing bookings keep their terms."""
from datetime import timedelta
from decimal import Decimal
from django.utils import timezone


def apply_package_rollout(registry, alias='default'):
    Tour, Departure, Day, Reservation = [registry.get_model('core', name) for name in
        ['Tour', 'TourDeparture', 'DepartureDay', 'Reservation']]
    today = timezone.localdate()
    for tour in Tour.objects.using(alias).all():
        price = Decimal('4100') if tour.country == 'morocco' else Decimal('4000')
        # This is an explicitly requested update to current catalogue prices.
        Tour.objects.using(alias).filter(pk=tour.pk).update(package_price=price, package_days=14, max_days=14)
        if 'Illustrative three-day programme' in tour.included:
            Tour.objects.using(alias).filter(pk=tour.pk).update(
                included=tour.included.replace('Illustrative three-day programme', 'Illustrative 14-day programme'))
    for country in Tour.objects.using(alias).values_list('country', flat=True).distinct():
        blocked = list(Reservation.objects.using(alias).filter(tour__country=country,
            status__in=['pending', 'booked'], end_date__gte=today).values_list('start_date', 'end_date'))
        departures = Departure.objects.using(alias).filter(tour__country=country).order_by('start_date', 'pk')
        for departure in departures:
            Departure.objects.using(alias).filter(pk=departure.pk).update(max_participants=20)
            # Do not move an existing group's dates or change its confirmed programme.
            if Reservation.objects.using(alias).filter(departure_id=departure.pk).exists():
                continue
            if departure.start_date < today:
                Departure.objects.using(alias).filter(pk=departure.pk).update(is_published=False)
                continue
            start = departure.start_date
            if departure.is_published:
                while True:
                    conflicts = [end for first, end in blocked
                        if first <= start + timedelta(days=13) and end >= start]
                    if not conflicts:
                        break
                    start = max(conflicts) + timedelta(days=1)
                blocked.append((start, start + timedelta(days=13)))
            Departure.objects.using(alias).filter(pk=departure.pk).update(
                start_date=start, end_date=start + timedelta(days=13), max_participants=20)
            for number in range(1, 15):
                Day.objects.using(alias).get_or_create(departure_id=departure.pk, day_number=number,
                    defaults={'title': f'Day {number}: programme to be confirmed', 'is_visible': True})
            Day.objects.using(alias).filter(departure_id=departure.pk, day_number__gt=14).delete()
            Day.objects.using(alias).filter(departure_id=departure.pk, day_number__lte=14).update(is_visible=True)
