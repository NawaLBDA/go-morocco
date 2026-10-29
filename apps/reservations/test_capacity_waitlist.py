from datetime import date, timedelta
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core import mail
from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TestCase, override_settings
from apps.core.models import Country, Destination, Tour, TourDeparture, Reservation, WaitlistEntry, Guide, BlogPost
from .availability import departure_capacity, has_conflict
from .views import _create_pending_reservation
from .waitlist import decide_waitlist, send_decision_email


@override_settings(SECURE_SSL_REDIRECT=False, EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', DEFAULT_FROM_EMAIL='travel@example.com')
class CapacityWaitlistTests(TestCase):
    def setUp(self):
        self.country = Country.objects.get(slug='morocco')
        self.users = [User.objects.create_user(f'traveler-{i}', email=f'traveler-{i}@example.com') for i in range(3)]
        self.staff = User.objects.create_superuser('capacity-manager', 'manager@example.com', 'test')
        self.tour = Tour.objects.create(title='Private Atlas journey', price_per_night=100,
            destination=Destination.objects.create(name='Atlas'))
        self.day = date.today() + timedelta(days=30)
        self.departure = TourDeparture.objects.create(tour=self.tour, start_date=self.day,
            end_date=self.day + timedelta(days=2), is_published=True, max_participants=7)

    def capacity(self, country=1, departure=1):
        self.country.max_concurrent_groups = country
        self.country.save()
        self.departure.max_concurrent_bookings = departure
        self.departure.save()

    def book(self, user=0, departure=None, persons=2):
        departure = departure or self.departure
        return _create_pending_reservation(user=self.users[user], tour=departure.tour,
            start_date=departure.start_date, end_date=departure.end_date, departure_id=departure.pk,
            persons=persons, payment_method='cash', full_package=False, include_transport=False,
            include_hotel=False, extra_activity_ids=[])

    def queue(self, user=1):
        self.client.force_login(self.users[user])
        return self.client.post(f'/departure/{self.departure.pk}/waitlist/',
            {'persons': 3, 'email': self.users[user].email, 'message': 'Three friends traveling together.'})

    def test_default_blocks_other_users_and_allows_smaller_groups(self):
        first = self.book(persons=1)[0]
        self.assertIsNotNone(first)
        self.assertEqual(self.book(user=1)[3], 409)
        self.assertEqual(self.book(user=2, persons=8)[3], 400)
        self.assertEqual(Reservation.objects.count(), 1)

    def test_parallel_groups_require_both_limits_and_counts_are_public_aggregates(self):
        self.capacity(country=2, departure=1)
        self.book(persons=3)
        self.assertEqual(self.book(user=1)[3], 409)
        self.capacity(country=2, departure=2)
        self.assertEqual(self.book(user=1, persons=2)[3], 200)
        self.assertEqual(self.book(user=2)[3], 409)
        self.departure.refresh_from_db()
        stats = departure_capacity(self.departure)
        self.assertEqual((stats['booked_groups'], stats['booked_travelers']), (2, 5))
        response = self.client.get('/reservations/', {'country': 'morocco'})
        self.assertContains(response, '5 travelers reserved')
        self.assertContains(response, 'Max 7')
        self.assertNotContains(response, self.users[0].email)

    def test_country_team_limit_still_applies_when_departure_allows_more(self):
        self.capacity(country=1, departure=3)
        self.book()
        self.assertEqual(self.book(user=1)[3], 409)

    def test_repeated_booking_for_same_user_is_not_a_second_group(self):
        self.capacity(country=3, departure=3)
        self.book()
        self.assertEqual(self.book()[3], 409)
        self.assertEqual(Reservation.objects.count(), 1)

    def test_multiple_date_ranges_get_separate_cards_and_independent_booking(self):
        second = TourDeparture.objects.create(tour=self.tour, start_date=self.day + timedelta(days=10),
            end_date=self.day + timedelta(days=12), is_published=True)
        self.book()
        self.assertEqual(self.book(user=1, departure=second)[3], 200)
        response = self.client.get('/reservations/', {'country': 'morocco'})
        self.assertEqual(sum(len(ds) for _, ds in response.context['departure_groups']), 2)
        self.assertContains(response, f'departure_id={self.departure.pk}')
        self.assertContains(response, f'departure_id={second.pk}')

    def test_api_honors_spare_capacity(self):
        self.capacity(country=2, departure=2)
        self.book()
        response = self.client.get('/api/guide-availability/', {'country': 'morocco',
            'tour_id': self.tour.pk, 'departure_id': self.departure.pk,
            'start_date': self.departure.start_date, 'end_date': self.departure.end_date})
        self.assertTrue(response.json()['available'])
        self.assertEqual(response.json()['booked_travelers'], 2)
        self.assertEqual(response.json()['blocked_ranges'], [])

    def test_spanning_disjoint_groups_uses_peak_capacity_not_total_count(self):
        self.capacity(country=2, departure=2)
        self.departure.end_date = self.day
        self.departure.save()
        self.book()
        later = TourDeparture.objects.create(tour=self.tour, start_date=self.day + timedelta(days=3),
            end_date=self.day + timedelta(days=3), is_published=True)
        self.assertEqual(self.book(user=1, departure=later)[3], 200)
        spanning = TourDeparture.objects.create(tour=self.tour, start_date=self.day,
            end_date=self.day + timedelta(days=3), is_published=True)
        self.assertEqual(self.book(user=2, departure=spanning)[3], 200)

    def test_waitlist_is_idempotent_and_holds_no_capacity(self):
        self.book()
        self.assertEqual(self.queue().status_code, 302)
        self.queue()
        self.assertEqual(WaitlistEntry.objects.count(), 1)
        self.assertEqual(Reservation.objects.count(), 1)
        self.assertEqual(WaitlistEntry.objects.get().status, 'waiting')
        self.assertEqual(len(mail.outbox), 0)

    def test_available_departures_cannot_be_waitlisted_and_bad_sizes_rejected(self):
        self.queue()
        self.assertFalse(WaitlistEntry.objects.exists())
        self.book()
        self.client.post(f'/departure/{self.departure.pk}/waitlist/', {'persons': 9, 'email': 'friend@example.com'})
        self.assertFalse(WaitlistEntry.objects.exists())

    def test_accept_rechecks_capacity_and_never_displaces_paid_group(self):
        first = self.book()[0]
        first.status, first.payment_status = 'booked', 'paid'
        first.save()
        self.queue()
        entry = WaitlistEntry.objects.get()
        with self.assertRaises(ValidationError):
            decide_waitlist(entry.pk, accept=True, staff=self.staff)
        first.refresh_from_db()
        entry.refresh_from_db()
        self.assertEqual((first.status, first.payment_status, entry.status), ('booked', 'paid', 'waiting'))
        self.assertEqual(Reservation.objects.count(), 1)

    def test_accept_after_capacity_increase_creates_confirmed_booking_and_one_email(self):
        self.book()
        self.queue()
        entry = WaitlistEntry.objects.get()
        self.capacity(country=2, departure=2)
        with self.captureOnCommitCallbacks(execute=True):
            decide_waitlist(entry.pk, accept=True, staff=self.staff, note='We have arranged a second guiding team.')
        entry.refresh_from_db()
        self.assertEqual(entry.status, 'accepted')
        self.assertEqual(entry.reservation.status, 'booked')
        self.assertEqual(entry.reservation.num_persons, 3)
        self.assertIsNotNone(entry.email_sent_at)
        self.assertEqual(mail.outbox[-1].to, [self.users[1].email])
        self.assertIn('We have arranged a second guiding team.', mail.outbox[-1].body)
        decide_waitlist(entry.pk, accept=True, staff=self.staff)
        send_decision_email(entry.pk)
        self.assertEqual(Reservation.objects.count(), 2)
        self.assertEqual(len(mail.outbox), 5)

    def test_rejection_notifies_user_and_email_failure_is_retryable(self):
        self.book()
        self.queue()
        entry = WaitlistEntry.objects.get()
        with patch('apps.reservations.waitlist.EmailMessage.send', side_effect=OSError('offline')):
            with self.captureOnCommitCallbacks(execute=True):
                decide_waitlist(entry.pk, accept=False, staff=self.staff, note='The other group is confirmed. Please consider another date.')
        entry.refresh_from_db()
        self.assertEqual(entry.status, 'rejected')
        self.assertTrue(entry.email_error)
        self.assertEqual(Reservation.objects.count(), 1)
        send_decision_email(entry.pk)
        entry.refresh_from_db()
        self.assertIsNotNone(entry.email_sent_at)
        self.assertIn('Please consider another date.', mail.outbox[-1].body)

    def test_dashboard_waitlist_buttons_are_staff_only_and_post_only(self):
        self.book()
        self.queue()
        entry = WaitlistEntry.objects.get()
        url = f'/dashboard/waitlist/{entry.pk}/reject/'
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertContains(self.client.get('/dashboard/reservations/'), 'Accept &amp; email')
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(url, {'decision_note': 'Try our next departure.'}).status_code, 302)
        self.assertEqual(WaitlistEntry.objects.get().status, 'rejected')

    def test_confirmed_guide_cannot_guide_two_groups_at_once(self):
        self.capacity(country=2, departure=2)
        first, second = self.book()[0], self.book(user=1)[0]
        guide = Guide.objects.create(country=self.country, name='Local guide', description='Our local expert.')
        first.assigned_guides.add(guide)
        with self.assertRaises(ValidationError), transaction.atomic():
            second.assigned_guides.add(guide)
        self.assertFalse(second.assigned_guides.exists())
        first.assigned_guides.clear()
        with self.assertRaises(ValidationError), transaction.atomic():
            guide.assigned_bookings.add(first, second)

    def test_deaf_packages_reject_non_deaf_waitlist(self):
        self.book()
        self.tour.deaf_only = True
        self.tour.save()
        self.assertEqual(self.queue().status_code, 302)
        self.assertFalse(WaitlistEntry.objects.exists())

    def test_country_first_catalogue_story_packs_and_year_navigation(self):
        japan = Country.objects.create(slug='japan', name='Japan', is_active=True)
        japanese = Tour.objects.create(title='Kyoto journey', country='japan', price_per_night=120,
            destination=Destination.objects.create(name='Kyoto', country='japan'))
        TourDeparture.objects.create(tour=japanese, start_date=self.day, end_date=self.day, is_published=True)
        BlogPost.objects.create(title='Atlas moments', slug='atlas-moments', country='morocco', content='Mountain stories.')
        BlogPost.objects.create(title='Kyoto moments', slug='kyoto-moments', country='japan', content='Kyoto stories.')
        response = self.client.get('/reservations/')
        self.assertTrue(response.context['country_picker'])
        self.assertContains(response, 'Explore Japan')
        response = self.client.get('/reservations/', {'country': 'japan', 'year': self.day.year})
        self.assertContains(response, 'Kyoto journey')
        self.assertNotContains(response, self.tour.title)
        response = self.client.get('/blog/', {'country': 'japan'})
        self.assertContains(response, 'Kyoto moments')
        self.assertNotContains(response, 'Atlas moments')
        self.assertContains(response, 'Journeys we remember.')
        self.assertNotContains(response, 'country-tours')
        self.assertEqual(self.client.get('/reservations/', {'year': 'bad'}).status_code, 404)
