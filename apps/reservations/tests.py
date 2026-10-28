from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Barrier

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse

from apps.core.models import Country, ContactMessage, Destination, GuideCalendar, Reservation, Tour, TourExtraActivity, TourDeparture
from apps.core.views import _is_range_available
from .views import _create_pending_reservation


class CalendarFixtures:
    def setUp(self):
        Country.objects.get_or_create(slug='morocco', defaults={'name': 'Morocco', 'is_active': True})
        Country.objects.get_or_create(slug='ireland', defaults={'name': 'Ireland'})
        self.day = date.today() + timedelta(days=30)
        self.user = User.objects.create_user('traveler-one', password='test-password')
        self.other = User.objects.create_user('traveler-two', password='test-password')
        destination = Destination.objects.create(name='Marrakech')
        self.tour = Tour.objects.create(title='Atlas', destination=destination, price_per_night=100)
        self.other_tour = Tour.objects.create(title='Sahara', destination=destination, price_per_night=150)
        self.ireland = Tour.objects.create(title='Dublin', destination=destination, price_per_night=90, country='ireland')
        GuideCalendar.objects.get_or_create(country='morocco')

    def book(self, *, user=None, tour=None, start=None, end=None):
        chosen_tour = tour or self.tour
        if chosen_tour.country == 'morocco':
            TourDeparture.objects.get_or_create(tour=chosen_tour, start_date=start or self.day,
                end_date=end or self.day + timedelta(days=3), defaults={'is_published': True})
        return _create_pending_reservation(
            user=user or self.user, tour=tour or self.tour,
            start_date=start or self.day, end_date=end or self.day + timedelta(days=3),
            persons=2, payment_method='cash', full_package=False,
            include_transport=False, include_hotel=False, extra_activity_ids=[],
        )


@override_settings(SECURE_SSL_REDIRECT=False)
class GuideCalendarTests(CalendarFixtures, TestCase):
    def test_other_tour_and_other_customer_conflict(self):
        first, error, _, _ = self.book()
        self.assertIsNone(error)
        second, error, _, status = self.book(user=self.other, tour=self.other_tour)
        self.assertIsNone(second)
        self.assertEqual(status, 409)
        first.refresh_from_db()
        self.assertEqual(first.status, 'pending')

    def test_same_customer_cannot_overlap_or_silently_replace(self):
        first, _, _, _ = self.book()
        second, _, _, status = self.book(tour=self.other_tour)
        self.assertIsNone(second)
        self.assertEqual(status, 409)
        first.refresh_from_db()
        self.assertEqual(first.status, 'pending')

    def test_disjoint_booking_keeps_confirmed_trip(self):
        first, _, _, _ = self.book()
        first.status = 'booked'
        first.save()
        second, error, info, _ = self.book(tour=self.other_tour,
            start=self.day + timedelta(days=5), end=self.day + timedelta(days=7))
        self.assertIsNone(error)
        self.assertIsNone(info)
        self.assertIsNotNone(second)
        first.refresh_from_db()
        self.assertEqual(first.status, 'booked')

    def test_inclusive_return_day_and_next_day(self):
        self.book()
        _, _, _, status = self.book(user=self.other, start=self.day + timedelta(days=3), end=self.day + timedelta(days=4))
        self.assertEqual(status, 409)
        reservation, error, _, _ = self.book(user=self.other, start=self.day + timedelta(days=4), end=self.day + timedelta(days=5))
        self.assertIsNone(error)
        self.assertIsNotNone(reservation)

    def test_all_overlap_shapes(self):
        self.book()
        for start, end in [(-1, 1), (2, 4), (-1, 4), (1, 2), (-2, 0)]:
            with self.subTest(start=start, end=end):
                _, _, _, status = self.book(user=self.other, start=self.day + timedelta(days=start), end=self.day + timedelta(days=end))
                self.assertEqual(status, 409)

    def test_inactive_reservations_release_dates(self):
        for status in ['rejected', 'cancelled', 'completed']:
            with self.subTest(status=status):
                Reservation.objects.all().delete()
                first, _, _, _ = self.book()
                first.status = status
                first.save()
                second, error, _, _ = self.book(user=self.other)
                self.assertIsNone(error)
                self.assertIsNotNone(second)

    def test_ireland_calendar_is_separate(self):
        self.book(tour=self.ireland)
        reservation, error, _, _ = self.book()
        self.assertIsNone(error)
        self.assertIsNotNone(reservation)

    def test_direct_create_and_admin_reactivation_cannot_bypass(self):
        self.book()
        with self.assertRaises(ValidationError):
            Reservation.objects.create(user=self.other, tour=self.other_tour,
                start_date=self.day, end_date=self.day + timedelta(days=2), total_price=200)
        inactive = Reservation.objects.create(user=self.other, tour=self.other_tour,
            start_date=self.day, end_date=self.day + timedelta(days=2), total_price=200, status='cancelled')
        inactive.status = 'booked'
        with self.assertRaises(ValidationError):
            inactive.save()

    def test_admin_update_conflict_preserves_original_dates(self):
        self.book()
        second, _, _, _ = self.book(user=self.other, start=self.day + timedelta(days=6), end=self.day + timedelta(days=8))
        self.other.is_staff = True
        self.other.save()
        self.client.force_login(self.other)
        response = self.client.post(reverse('admin_update_reservation', args=[second.pk]), {
            'start_date': self.day.isoformat(), 'end_date': (self.day + timedelta(days=2)).isoformat(),
            'status': 'booked', 'num_persons': '2',
        })
        self.assertEqual(response.status_code, 302)
        second.refresh_from_db()
        self.assertEqual(second.start_date, self.day + timedelta(days=6))

    def test_admin_validation_handles_conflict(self):
        self.book()
        inactive = Reservation.objects.create(user=self.other, tour=self.other_tour,
            start_date=self.day, end_date=self.day + timedelta(days=2), total_price=200, status='rejected')
        self.other.is_staff = True
        self.other.save()
        self.client.force_login(self.other)
        response = self.client.post(reverse('validate_reservation', args=[inactive.pk]))
        self.assertEqual(response.status_code, 302)
        inactive.refresh_from_db()
        self.assertEqual(inactive.status, 'rejected')

    def test_api_and_chat_include_own_bookings_without_personal_data(self):
        self.book()
        self.client.force_login(self.user)
        response = self.client.get('/morocco/api/guide-availability/', {
            'start_date': self.day.isoformat(), 'end_date': (self.day + timedelta(days=2)).isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['available'])
        self.assertEqual(set(response.json()['blocked_ranges'][0]), {'from', 'to'})
        self.assertFalse(_is_range_available('morocco', self.day, self.day + timedelta(days=2), exclude_user=self.user))
        detail = self.client.get('/morocco/tour/' + self.other_tour.slug + '/')
        self.assertEqual(len(detail.context['disabled_ranges']), 1)

    def test_api_invalid_dates_and_country(self):
        for start, end in [('invalid', 'invalid'), (self.day.isoformat(), (self.day - timedelta(days=1)).isoformat()),
                           ((date.today() - timedelta(days=1)).isoformat(), self.day.isoformat())]:
            self.assertEqual(self.client.get('/morocco/api/guide-availability/', {'start_date': start, 'end_date': end}).status_code, 400)
        self.assertEqual(self.client.get('/ireland/api/guide-availability/').status_code, 404)

    def test_long_morocco_trip_prices_and_reserves_entire_calendar(self):
        self.tour.max_days = 19
        self.tour.save()
        end = self.day + timedelta(days=10)
        query = {'start_date': self.day.isoformat(), 'end_date': end.isoformat()}
        response = self.client.get('/morocco/api/guide-availability/', query)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['available'])
        reservation, error, _, status = self.book(end=end)
        self.assertIsNone(error)
        self.assertEqual(status, 200)
        self.assertEqual(reservation.total_price, 2200)
        response = self.client.get('/morocco/api/guide-availability/', query)
        self.assertFalse(response.json()['available'])
        _, _, _, status = self.book(user=self.other, tour=self.other_tour,
            start=end - timedelta(days=1), end=end + timedelta(days=1))
        self.assertEqual(status, 409)

    def test_ireland_duration_limit_is_unchanged(self):
        reservation, _, _, status = self.book(tour=self.ireland, end=self.day + timedelta(days=6))
        self.assertIsNone(reservation)
        self.assertEqual(status, 400)

    def test_search_keeps_reserved_departures_visible_for_waitlist_review(self):
        response = self.client.get('/morocco/reservations/', {
            'start_date': self.day.isoformat(), 'end_date': (self.day + timedelta(days=3)).isoformat(),
        })
        self.assertEqual(response.context['search_start_date'], self.day.isoformat())
        self.book()
        response = self.client.get('/morocco/reservations/', {
            'start_date': self.day.isoformat(), 'end_date': (self.day + timedelta(days=3)).isoformat(),
        })
        self.assertContains(response, 'Fully reserved')
        self.assertContains(response, 'View &amp; join waiting list')
        self.assertTrue(all(not departure.available for _, departures in response.context['departure_groups'] for departure in departures))

    def test_web_and_chat_submission_paths_both_reject_overlap(self):
        self.book()
        self.client.force_login(self.other)
        payload = {'tour_id': self.other_tour.id, 'start_date': self.day.isoformat(),
            'end_date': (self.day + timedelta(days=2)).isoformat(), 'persons': 2, 'payment_method': 'cash'}
        response = self.client.post('/morocco/api/chat-book-tour/', payload, content_type='application/json')
        self.assertEqual(response.status_code, 409)
        response = self.client.post(f'/morocco/tour/{self.other_tour.pk}/book/', payload)
        self.assertEqual(response.status_code, 302)
        self.assertIn('start_date=' + self.day.isoformat(), response.url)
        self.assertEqual(Reservation.objects.count(), 1)

    def test_unselected_extras_are_not_charged(self):
        TourExtraActivity.objects.create(tour=self.tour, title='Optional visit', price=50)
        reservation, error, _, _ = self.book()
        self.assertIsNone(error)
        self.assertEqual(reservation.selected_extra_activities, [])
        self.assertEqual(reservation.total_price, 800)

    def test_contact_invalid_input_preserves_message_and_does_not_save(self):
        response = self.client.post('/morocco/contact/', {
            'name': 'Traveler', 'email': 'invalid-email', 'subject': 'Trip', 'message': 'Please help with my itinerary.',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please help with my itinerary.')
        self.assertContains(response, 'Please check the details below.')
        self.assertFalse(ContactMessage.objects.exists())

    def test_contact_enquiry_does_not_reserve_calendar(self):
        response = self.client.post('/morocco/contact/', {
            'name': 'Traveler', 'email': 'traveler@example.com', 'subject': 'Trip', 'message': 'Please help with my itinerary.',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ContactMessage.objects.count(), 1)
        self.assertFalse(Reservation.objects.exists())


class GuideConcurrencyTests(CalendarFixtures, TransactionTestCase):
    @skipUnlessDBFeature('has_select_for_update')
    def test_three_requests_cannot_exceed_two_group_slots(self):
        Country.objects.filter(slug='morocco').update(max_concurrent_groups=2)
        TourDeparture.objects.create(tour=self.tour, start_date=self.day,
            end_date=self.day + timedelta(days=3), is_published=True, max_concurrent_bookings=2)
        third = User.objects.create_user('third-traveler')
        barrier = Barrier(3)
        def submit(user_id):
            close_old_connections()
            try:
                user, tour = User.objects.get(pk=user_id), Tour.objects.get(pk=self.tour.pk)
                barrier.wait(timeout=10)
                return self.book(user=user, tour=tour)[3]
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(submit, [self.user.pk, self.other.pk, third.pk]))
        self.assertEqual(sorted(results), [200, 200, 409])
        self.assertEqual(Reservation.objects.count(), 2)

    @skipUnlessDBFeature('has_select_for_update')
    def test_simultaneous_requests_only_one_wins_on_empty_calendar(self):
        barrier = Barrier(2)
        def submit(user_id, tour_id):
            close_old_connections()
            try:
                user, tour = User.objects.get(pk=user_id), Tour.objects.get(pk=tour_id)
                barrier.wait(timeout=10)
                return self.book(user=user, tour=tour)[3]
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(submit, self.user.pk, self.tour.pk)
            second = pool.submit(submit, self.other.pk, self.other_tour.pk)
            self.assertEqual(sorted([first.result(timeout=20), second.result(timeout=20)]), [200, 409])
        self.assertEqual(Reservation.objects.count(), 1)
