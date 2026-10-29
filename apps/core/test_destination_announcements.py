from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from .models import Country, Tour, TourDeparture, Destination
from .catalogue import visible_tours
from apps.reservations.views import _create_pending_reservation


@override_settings(SECURE_SSL_REDIRECT=False)
class DestinationAnnouncementTests(TestCase):
    def test_announcement_hides_prices_and_rejects_booking(self):
        country, _ = Country.objects.update_or_create(slug='nigeria', defaults={
            'name': 'Nigeria', 'is_active': True, 'coming_soon': True})
        tour = Tour.objects.create(country='nigeria', title='Hidden example', price_per_night=999,
            destination=Destination.objects.create(country='nigeria', name='Lagos'))
        day = timezone.localdate() + timedelta(days=90)
        departure = TourDeparture.objects.create(tour=tour, start_date=day, end_date=day, is_published=True)
        user = User.objects.create_user('announcement-test', email='test@example.com')
        self.assertFalse(visible_tours(user).filter(pk=tour.pk).exists())
        response = self.client.get('/', {'country': 'nigeria'})
        self.assertContains(response, 'Nigeria is in the works.')
        self.assertNotContains(response, 'Hidden example')
        self.assertNotContains(response, '$999')
        self.assertEqual(self.client.get(f'/tour/{tour.slug}/').status_code, 404)
        result = _create_pending_reservation(user=user, tour=tour, start_date=day, end_date=day,
            persons=1, payment_method='cash', full_package=False, include_transport=False,
            include_hotel=False, extra_activity_ids=[], departure_id=departure.pk)
        self.assertIsNone(result[0])
        country.coming_soon = False
        country.save()
        self.assertTrue(visible_tours(user).filter(pk=tour.pk).exists())

    def test_four_destinations_and_favicon(self):
        response = self.client.get('/')
        for name in ('Nigeria', 'Morocco', 'Ireland', 'Jamaica'):
            self.assertContains(response, name)
        self.assertContains(response, 'In the works: dates and prices to be announced')
        self.assertContains(response, '/static/favicon.ico?v=3')
        self.assertRedirects(self.client.get('/favicon.ico'), '/static/favicon.ico?v=3', fetch_redirect_response=False)
