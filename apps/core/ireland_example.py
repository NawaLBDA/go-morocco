"""One editable Ireland starter trip; repeat runs preserve staff edits."""
from datetime import timedelta
from django.utils import timezone


def seed_ireland_example(registry, alias='default'):
    Country, Destination, Tour, Activity, Departure, Day, Reservation = [
        registry.get_model('core', name) for name in
        ['Country', 'Destination', 'Tour', 'TourActivity', 'TourDeparture', 'DepartureDay', 'Reservation']]
    country, _ = Country.objects.using(alias).get_or_create(slug='ireland', defaults={
        'name': 'Ireland', 'is_active': True, 'uses_scheduled_departures': True})
    Country.objects.using(alias).filter(pk=country.pk).update(uses_scheduled_departures=True)
    if not country.introduction:
        Country.objects.using(alias).filter(pk=country.pk).update(
            introduction='Dublin stories, harbour walks and a gentler pace along the Irish coast.')
    if Tour.objects.using(alias).filter(slug='demo-dublin-howth-culture').exists():
        return
    destination, _ = Destination.objects.using(alias).get_or_create(country='ireland', name='Dublin & Howth',
        defaults={'region_id': 'ireland'})
    tour = Tour.objects.using(alias).create(country='ireland', region_id='ireland', destination=destination,
        slug='demo-dublin-howth-culture', title='Dublin & Howth: stories by the sea', price_per_night=140,
        max_days=3, description='Discover Dublin through its streets, gardens and local stories, then slow down beside Howth harbour. Starter example: dates, prices and visits are illustrative. AI-generated destination images. Arrangements require team confirmation.',
        included='Illustrative three-day programme\nItinerary planning',
        not_included='Flights\nAccommodation and meals unless confirmed\nTravel insurance\nUnconfirmed transfers and entry fees')
    stops = [
        ('Trinity College surroundings', '53.3438', '-6.2546'), ('St Stephen\'s Green', '53.3382', '-6.2591'),
        ('Dublin Castle surroundings', '53.3430', '-6.2674'), ('River Liffey walk', '53.3469', '-6.2633'),
        ('Howth harbour', '53.3913', '-6.0664'), ('Howth village', '53.3870', '-6.0655')]
    by_day = {}
    for index, (title, latitude, longitude) in enumerate(stops):
        number = index // 2 + 1
        activity = Activity.objects.using(alias).create(tour=tour, title=title, place_name=title,
            city='Howth' if number == 3 else 'Dublin', day_number=number, display_order=index,
            latitude=latitude, longitude=longitude, point_role='start' if index % 2 == 0 else 'end',
            description='Illustrative itinerary stop. Access, timing and transport are confirmed by the team.')
        by_day.setdefault(number, []).append(activity)
    start = timezone.localdate() + timedelta(days=90)
    while Reservation.objects.using(alias).filter(tour__country='ireland', status__in=['pending', 'booked'],
            start_date__lte=start + timedelta(days=2), end_date__gte=start).exists():
        start += timedelta(days=4)
    departure = Departure.objects.using(alias).create(tour=tour, start_date=start,
        end_date=start + timedelta(days=2), is_published=True, max_participants=8, max_concurrent_bookings=1)
    for number, activities in by_day.items():
        day, _ = Day.objects.using(alias).get_or_create(departure_id=departure.pk, day_number=number,
            defaults={'title': f'Dublin & Howth discoveries - day {number}'})
        day.activities.add(*activities)
