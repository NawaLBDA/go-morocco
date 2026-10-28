"""Editable Rabat example. Never replaces staff content or booked programmes."""
from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from apps.core.models import Country, Destination, Tour, TourActivity, TourDeparture, TourItineraryLeg, BlogPost


class Command(BaseCommand):
    help = 'Add a three-day Rabat example, two published example departures and an editorial story.'

    @transaction.atomic
    def handle(self, *args, **options):
        Country.objects.get_or_create(slug='morocco', defaults={'name': 'Morocco', 'is_active': True})
        destination, _ = Destination.objects.get_or_create(country='morocco', name='Rabat')
        tour = Tour.objects.filter(country='morocco', destination=destination).order_by('pk').first()
        if not tour:
            tour = Tour.objects.create(country='morocco', destination=destination, title='Rabat: The City of Light',
                slug='rabat-the-city-of-light', price_per_night=100, max_days=3,
                description='From the Bouregreg riverfront to the lanes of the Kasbah, discover Rabat at a gentler pace.')
        if tour.max_days < 3:
            raise CommandError('Rabat needs a maximum duration of at least three days. Existing settings were preserved.')
        existing_days = set(tour.activity_cards.values_list('day_number', flat=True))
        added_days = set()
        stops = [
            (1, 'Hassan Tower', 'Discover Rabat’s monumental heritage.', '34.024167', '-6.822778'),
            (1, 'Mohammed V Mausoleum', 'Explore the architectural setting with your guide.', '34.022700', '-6.821800'),
            (1, 'Bouregreg riverfront', 'Enjoy a slower moment by the river.', '34.028000', '-6.827000'),
            (2, 'Bab Oudaia', 'Begin among the gateways and lanes of the Kasbah.', '34.031000', '-6.836000'),
            (2, 'Andalusian Gardens', 'Pause among the gardens.', '34.030800', '-6.834000'),
            (2, 'Kasbah viewpoint', 'Look towards the Atlantic and the Bouregreg.', '34.033000', '-6.836000'),
            (3, 'Chellah', 'Discover another layer of Rabat’s heritage.', '34.006600', '-6.820600'),
            (3, 'Rabat medina', 'Finish with a walk through the old city.', '34.025000', '-6.841000'),
        ]
        previous = None
        for index, (day, title, description, lat, lng) in enumerate(stops):
            if day in existing_days:
                continue
            added_days.add(day)
            stop = TourActivity.objects.create(tour=tour, title=title, city='Rabat', place_name=title,
                day_number=day, display_order=index, latitude=lat, longitude=lng,
                point_role='start' if index == 0 else 'end' if index == len(stops)-1 else 'regular',
                description=description + ' Illustrative programme; exact visits and arrangements are confirmed by the team.')
            if previous and previous.day_number == day:
                TourItineraryLeg.objects.create(tour=tour, from_activity=previous, to_activity=stop,
                    distance_label='Illustrative connection', transport_mode='private' if day == 3 else 'walk', display_order=index)
            previous = stop
        departures = list(tour.departures.filter(is_published=True, start_date__gte=timezone.localdate()).order_by('start_date'))
        for offset in (30, 60)[len(departures):]:
            start = timezone.localdate() + timedelta(days=offset)
            departure, _ = TourDeparture.objects.get_or_create(tour=tour, start_date=start, end_date=start+timedelta(days=2),
                defaults={'is_published': True, 'max_participants': 8, 'max_concurrent_bookings': 1})
            departures.append(departure)
        for departure in departures:
            if not departure.reservations.filter(status__in=['pending', 'booked', 'completed']).exists():
                for day in departure.program_days.filter(day_number__in=added_days):
                    if not day.activities.exists():
                        day.activities.add(*tour.activity_cards.filter(day_number=day.day_number))
        BlogPost.objects.get_or_create(slug='rabat-between-river-and-ocean', defaults={
            'country': 'morocco', 'title': 'Rabat, between river and ocean', 'image': tour.image,
            'content': 'Rabat rewards a slower look. Its monumental landmarks, medina and riverfront offer different ways to discover Morocco’s capital.\n\nStart with the setting around Hassan Tower and the Mohammed V Mausoleum. Make time for the lanes of the Kasbah of the Oudaia and a pause near the Atlantic. Chellah adds another perspective on the city’s layered heritage.\n\nThis sample editorial accompanies our illustrative three-day Rabat itinerary. It is inspiration for planning, rather than a report of a completed group journey. Dates, access, transport and visits should be confirmed with our team.'})
        self.stdout.write(self.style.SUCCESS('Rabat example ready. Sample dates, coordinates and connections are editable in Django admin.'))
        for departure in departures:
            self.stdout.write(f'/tour/{tour.slug}/?departure_id={departure.pk} ({departure.start_date} to {departure.end_date})')
