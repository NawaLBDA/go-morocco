from datetime import timedelta
from decimal import Decimal
from django.apps import apps
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone
from .models import Country, Destination, Tour, TourDeparture, Reservation, Promotion
from .package_rollout import apply_package_rollout
from apps.reservations.views import _create_pending_reservation


@override_settings(SECURE_SSL_REDIRECT=False, EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PackageRolloutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('package-traveler', email='traveler@example.com')
        self.tour = Tour.objects.create(title='Rabat package', country='morocco', price_per_night=100,
            destination=Destination.objects.create(name='Rabat'))
        start = timezone.localdate() + timedelta(days=80)
        self.departure = TourDeparture.objects.create(tour=self.tour, start_date=start,
            end_date=start + timedelta(days=2), is_published=True, max_participants=8)

    def book(self, persons=2):
        self.tour.refresh_from_db()
        self.departure.refresh_from_db()
        return _create_pending_reservation(user=self.user, tour=self.tour,
            start_date=self.departure.start_date, end_date=self.departure.end_date,
            departure_id=self.departure.pk, persons=persons, payment_method='cash', full_package=False,
            include_transport=False, include_hotel=False, extra_activity_ids=[])

    def test_full_package_total_is_not_multiplied_by_days_or_discounted_below_minimum(self):
        apply_package_rollout(apps)
        self.tour.refresh_from_db()
        self.departure.refresh_from_db()
        self.assertEqual(self.tour.package_price, Decimal('4100'))
        self.assertEqual(self.departure.duration_days, 14)
        self.assertEqual(self.departure.active_days, 14)
        self.assertEqual(self.departure.max_participants, 20)
        Promotion.objects.create(country='morocco', name='Legacy offer', active=True, percent=40, apply_to_all=True)
        self.assertEqual(self.book(21)[3], 400)
        reservation, error, _, status = self.book(20)
        self.assertIsNone(error)
        self.assertEqual(status, 200)
        self.assertEqual(reservation.total_price, Decimal('82000'))
        self.assertTrue(reservation.package_priced)
        self.assertEqual(reservation.booked_days, 14)
        self.assertEqual(reservation.base_price_per_night, Decimal('4100'))

    def test_existing_booking_dates_and_total_remain_unchanged(self):
        booking = self.book()[0]
        original = (booking.start_date, booking.end_date, booking.total_price)
        apply_package_rollout(apps)
        booking.refresh_from_db()
        self.departure.refresh_from_db()
        self.assertEqual((booking.start_date, booking.end_date, booking.total_price), original)
        self.assertEqual(self.departure.duration_days, 3)
        self.assertFalse(booking.package_priced)
        self.user.is_staff = True
        self.user.save()
        self.client.force_login(self.user)
        self.client.post(f'/dashboard/reservation/{booking.pk}/update/', {
            'start_date': booking.start_date, 'end_date': booking.end_date, 'num_persons': 2})
        booking.refresh_from_db()
        self.assertEqual(booking.total_price, original[2])

    def test_departures_are_shifted_without_overlaps_and_prices_validate(self):
        second = TourDeparture.objects.create(tour=self.tour,
            start_date=self.departure.start_date + timedelta(days=4),
            end_date=self.departure.end_date + timedelta(days=4), is_published=True)
        apply_package_rollout(apps)
        self.departure.refresh_from_db()
        second.refresh_from_db()
        self.assertGreater(second.start_date, self.departure.end_date)
        self.assertEqual(second.duration_days, 14)
        self.tour.refresh_from_db()
        self.tour.package_price = 3999
        with self.assertRaises(ValidationError):
            self.tour.full_clean()

    def test_country_can_be_hidden_independently_of_announcements(self):
        country = Country.objects.get(slug='morocco')
        country.is_visible = False
        country.save()
        self.assertEqual(self.client.get('/', {'country': 'morocco'}).status_code, 404)
        self.assertEqual(self.client.get(f'/tour/{self.tour.slug}/').status_code, 404)
        self.assertNotIn('morocco', [row.slug for row in self.client.get('/').context['countries']])
        self.assertEqual(self.book()[3], 404)
        self.assertTrue(Tour.objects.filter(pk=self.tour.pk).exists())
        country.is_visible = True
        country.save()
        self.assertEqual(self.client.get('/', {'country': 'morocco'}).status_code, 200)
