from io import StringIO
from django.core.management import call_command
from django.test import TestCase, override_settings
from .models import Tour, BlogPost, Country, Destination, TourActivity, TourDeparture
from datetime import timedelta
from django.utils import timezone
from .views import _build_itinerary_days


@override_settings(SECURE_SSL_REDIRECT=False)
class RabatPreviewTests(TestCase):
    def test_labeled_departure_example_is_repeatable_and_keeps_regular_dates(self):
        call_command('seed_rabat_preview', stdout=StringIO())
        call_command('seed_deaf_departure_preview', stdout=StringIO())
        tour = Tour.objects.get(slug='rabat-the-city-of-light')
        self.assertEqual(tour.departures.count(), 3)
        self.assertEqual(tour.departures.filter(deaf_only=True).count(), 1)
        call_command('seed_deaf_departure_preview', stdout=StringIO())
        self.assertEqual(tour.departures.count(), 3)
        response = self.client.get('/', {'country': 'morocco'})
        self.assertContains(response, 'Deaf travelers only', count=1)
        self.assertContains(response, 'class="journey-grid dated-grid"', count=1)

    def test_seed_is_repeatable_preserves_edits_and_provides_map_points(self):
        call_command('seed_rabat_preview', stdout=StringIO())
        tour = Tour.objects.get(slug='rabat-the-city-of-light')
        departure = tour.departures.first()
        self.assertEqual(tour.departures.count(), 2)
        self.assertEqual(tour.activity_cards.count(), 8)
        self.assertEqual(tour.itinerary_legs.count(), 5)
        programme = _build_itinerary_days(tour, departure=departure)
        self.assertEqual(len(programme), 3)
        self.assertIn('34.024', str(programme))
        stop = tour.activity_cards.first()
        stop.description = 'Team edited this stop'
        stop.save()
        call_command('seed_rabat_preview', stdout=StringIO())
        stop.refresh_from_db()
        self.assertEqual(stop.description, 'Team edited this stop')
        self.assertEqual(tour.departures.count(), 2)
        self.assertEqual(tour.activity_cards.count(), 8)
        self.assertEqual(BlogPost.objects.filter(slug='rabat-between-river-and-ocean').count(), 1)

    def test_existing_first_day_is_preserved_and_missing_days_are_added(self):
        Country.objects.get_or_create(slug='morocco', defaults={'name': 'Morocco'})
        tour = Tour.objects.create(title='Existing Rabat', country='morocco', price_per_night=100,
            destination=Destination.objects.create(country='morocco', name='Rabat'))
        stop = TourActivity.objects.create(tour=tour, title='Team planned visit', day_number=1)
        start = timezone.localdate() + timedelta(days=30)
        departure = TourDeparture.objects.create(tour=tour, start_date=start, end_date=start+timedelta(days=2), is_published=True)
        call_command('seed_rabat_preview', stdout=StringIO())
        self.assertEqual(list(departure.program_days.get(day_number=1).activities.all()), [stop])
        self.assertEqual(departure.program_days.get(day_number=2).activities.count(), 3)
        self.assertEqual(departure.program_days.get(day_number=3).activities.count(), 2)
