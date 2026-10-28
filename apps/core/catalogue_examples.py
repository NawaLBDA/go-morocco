"""Versioned, additive starter content for the explicitly requested Render catalogue."""
from datetime import timedelta
from django.utils import timezone


EXAMPLES = [
    ('morocco', 'Rabat', 'demo-rabat-culture', 'Rabat: riverside stories & the kasbah', 100, 8, 30,
     'Explore the riverfront, the lanes of the Kasbah and the layers of Morocco\'s capital at a relaxed pace.', [
         ('Hassan Tower', '34.024167', '-6.822778'), ('Mohammed V Mausoleum surroundings', '34.022700', '-6.821800'),
         ('Kasbah of the Oudaia', '34.031000', '-6.836000'), ('Andalusian Gardens', '34.030800', '-6.834000'),
         ('Chellah', '34.006600', '-6.820600'), ('Rabat medina', '34.025000', '-6.837000')]),
    ('morocco', 'Marrakech', 'demo-marrakech-culture', 'Marrakech: medina, gardens & craft', 145, 8, 38,
     'Discover Marrakech through its medina, garden settings and craft traditions, with room to pause and connect.', [
         ('Koutoubia surroundings', '31.623800', '-7.993600'), ('Jemaa el-Fna', '31.625800', '-7.989100'),
         ('Bahia Palace', '31.620700', '-7.980500'), ('Medina craft lanes', '31.631000', '-7.984000'),
         ('Menara Gardens', '31.612000', '-8.036000'), ('Marrakech city walls', '31.642000', '-7.999000')]),
    ('morocco', 'Tangier', 'demo-tangier-culture', 'Tangier: sea views & cultural crossroads', 110, 8, 46,
     'Follow Tangier\'s old-city lanes and coastal horizons in a starter journey shaped around culture and connection.', [
         ('Tangier medina', '35.787000', '-5.812000'), ('Kasbah neighbourhood', '35.789000', '-5.813000'),
         ('Grand Socco', '35.784000', '-5.813000'), ('Mendoubia Gardens', '35.785000', '-5.814000'),
         ('Tangier waterfront', '35.777000', '-5.798000'), ('Cape Spartel area', '35.791000', '-5.922000')]),
    ('nigeria', 'Lagos', 'demo-lagos-culture', 'Lagos: art, city life & green escapes', 135, 6, 33,
     'An introduction to Lagos through creative spaces, city stories and a nature-focused pause on the Lekki peninsula.', [
         ('Freedom Park area', '6.447000', '3.397000'), ('National Museum Lagos', '6.443000', '3.403000'),
         ('Nike Art Gallery area', '6.431000', '3.458000'), ('Lekki Conservation Centre', '6.441000', '3.536000'),
         ('Victoria Island', '6.429000', '3.421000'), ('Lagos Lagoon views', '6.450000', '3.430000')]),
    ('nigeria', 'Abuja', 'demo-abuja-culture', 'Abuja: crafts, green spaces & connections', 125, 6, 41,
     'Find a gentler introduction to Nigeria\'s capital through craft discoveries, open spaces and time for conversation.', [
         ('Abuja Arts and Crafts Village', '9.065000', '7.484000'), ('Millennium Park', '9.078000', '7.495000'),
         ('Jabi Lake area', '9.074000', '7.418000'), ('Wuse neighbourhood', '9.071000', '7.462000'),
         ('Central Abuja', '9.057000', '7.489000'), ('City garden walk', '9.061000', '7.487000')]),
]


def seed_examples(registry, alias='default', *, activate_countries=False, today=None):
    """Only new reserved slugs get a programme; later staff edits are left alone."""
    today = today or timezone.localdate()
    Country, Destination, Tour, Activity, Leg, Departure, Day, Blog, Reservation = [registry.get_model('core', name)
        for name in ['Country', 'Destination', 'Tour', 'TourActivity', 'TourItineraryLeg', 'TourDeparture', 'DepartureDay', 'BlogPost', 'Reservation']]
    for slug, name, intro in [
        ('morocco', 'Morocco', 'Medina lanes, riverside stories and coastal horizons. Discover Rabat, Marrakech and Tangier.'),
        ('nigeria', 'Nigeria', 'Art, craft, city life and meaningful connections. Start exploring with our Lagos and Abuja examples.'),
    ]:
        country, _ = Country.objects.using(alias).get_or_create(slug=slug, defaults={
            'name': name, 'is_active': True, 'introduction': intro})
        updates = {}
        if activate_countries and not country.is_active:
            updates['is_active'] = True
        if not country.introduction:
            updates['introduction'] = intro
        if updates:
            Country.objects.using(alias).filter(pk=country.pk).update(**updates)
    created_tours = created_departures = 0
    for country, city, slug, title, rate, capacity, offset, description, stops in EXAMPLES:
        # A saved slug is the marker: re-running does not recreate removed dates or overwrite a programme.
        if Tour.objects.using(alias).filter(slug=slug).exists():
            continue
        destination = Destination.objects.using(alias).filter(country=country, name__iexact=city).first()
        if not destination:
            destination = Destination.objects.using(alias).create(country=country, region_id=country, name=city)
        existing_image = Tour.objects.using(alias).filter(country=country, destination_id=destination.pk).exclude(
            image__isnull=True).exclude(image='').values_list('image', flat=True).first()
        tour = Tour.objects.using(alias).create(country=country, region_id=country, destination=destination,
            slug=slug, title=title, price_per_night=rate, max_days=3, image=existing_image or None,
            description=description + '\n\nStarter example: dates, prices and visits are illustrative and subject to team confirmation. The Deaf-labelled departures welcome everyone; please discuss sign-language and communication arrangements with our team before confirmation.',
            included='Illustrative three-day programme\nTrip planning with the team\nGuidance arrangements subject to confirmation',
            not_included='Flights\nAccommodation and meals unless separately confirmed\nTravel insurance\nUnconfirmed entry fees and transfers')
        created_tours += 1
        by_day = {}
        previous = None
        for index, (place, lat, lon) in enumerate(stops):
            number = index // 2 + 1
            activity = Activity.objects.using(alias).create(tour=tour, title=place, place_name=place,
                city=city, day_number=number, display_order=index, latitude=lat, longitude=lon,
                point_role='start' if index % 2 == 0 else 'end',
                description='Suggested stop in this starter itinerary. Access, timing and communication support are confirmed by our team. Map coordinates and connections are approximate examples.')
            by_day.setdefault(number, []).append(activity)
            if previous and index % 2:
                Leg.objects.using(alias).create(tour=tour, from_activity=previous, to_activity=activity,
                    distance_label='Illustrative connection', transport_mode='private', display_order=index)
            previous = activity
        for extra_days, deaf in [(0, False), (26, True)]:
            start = today + timedelta(days=offset + extra_days)
            while Reservation.objects.using(alias).filter(tour__country=country, status__in=['pending', 'booked'],
                    start_date__lte=start + timedelta(days=2), end_date__gte=start).exists():
                start += timedelta(days=4)
            departure = Departure.objects.using(alias).create(tour=tour, start_date=start,
                end_date=start + timedelta(days=2), is_published=True, max_participants=capacity,
                max_concurrent_bookings=1, deaf_only=deaf)
            created_departures += 1
            for number, activities in by_day.items():
                day, _ = Day.objects.using(alias).get_or_create(departure_id=departure.pk, day_number=number,
                    defaults={'title': f'{city} discoveries - day {number}'})
                day.activities.add(*activities)
    for country, slug, title, content in [
        ('morocco', 'starter-morocco-city-connections', 'Morocco: three cities, many connections',
         'Rabat, Marrakech and Tangier offer different starting points for a journey through Morocco. Think riverfront discoveries, medina lanes, garden pauses and coastal horizons.\n\nThese starter itineraries are planning inspiration, not reports of completed group trips. The published example dates and prices can be adjusted with our team. Deaf-labelled departures welcome everyone; communication arrangements should be discussed before confirmation.'),
        ('nigeria', 'starter-nigeria-city-connections', 'Nigeria: art, city life and shared discoveries',
         'Our Nigeria collection begins with Lagos and Abuja: starting points for exploring art, craft, green spaces and the connections that give travel meaning.\n\nThis is starter editorial content, not a report of a completed group journey. Visits and access remain subject to confirmation. Deaf-labelled departures welcome everyone; sign-language and communication support must be discussed with the team.'),
    ]:
        Blog.objects.using(alias).get_or_create(slug=slug, defaults={
            'country': country, 'region_id': country, 'title': title, 'content': content})
    return {'tours_created': created_tours, 'departures_created': created_departures}
