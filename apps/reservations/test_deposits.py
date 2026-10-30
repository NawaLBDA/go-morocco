from datetime import timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from apps.core.models import Tour, Destination, TourDeparture, BookingNotification
from .views import _create_pending_reservation
from .deposits import record_deposit_received


@override_settings(SECURE_SSL_REDIRECT=False, EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class DepositWorkflowTests(TestCase):
    def setUp(self):
        self.traveler = User.objects.create_user('deposit-traveler', email='traveler@example.com')
        self.staff = User.objects.create_user('deposit-manager', is_staff=True, email='manager@example.com')
        self.tour = Tour.objects.create(title='Rabat deposit example', package_price=4000, price_per_night=0, min_travelers=2,
            destination=Destination.objects.create(name='Rabat'), deposit_enabled=True)
        start = timezone.localdate() + timedelta(days=100)
        self.departure = TourDeparture.objects.create(tour=self.tour, start_date=start,
            end_date=start + timedelta(days=13), is_published=True)

    def book(self, people):
        booking, error, _, status = _create_pending_reservation(user=self.traveler, tour=self.tour,
            start_date=self.departure.start_date, end_date=self.departure.end_date, persons=people,
            departure_id=self.departure.pk, payment_method='cash', full_package=False,
            include_transport=False, include_hotel=False, extra_activity_ids=[])
        self.assertIsNone(error)
        self.assertEqual(status, 200)
        return booking

    def test_one_person_is_allowed_without_group_deposit(self):
        self.tour.min_travelers = 1
        self.tour.save()
        booking = self.book(1)
        self.assertEqual(self.tour.min_travelers, 1)
        self.assertEqual(booking.total_price, Decimal('4000'))
        self.assertEqual(booking.deposit_status, 'not_required')
        booking.status = 'booked'
        booking.save()

    def test_disabled_deposit_does_not_affect_group_requests(self):
        self.tour.deposit_enabled = False
        self.tour.save()
        self.assertFalse(self.book(5).deposit_pending)

    def test_minimum_one_disables_deposit_even_for_a_larger_group(self):
        self.tour.min_travelers = 1
        self.tour.save()
        booking = self.book(5)
        self.assertEqual(booking.total_price, Decimal('20000'))
        self.assertFalse(booking.deposit_pending)
        response = self.client.get(f'/tour/{self.tour.slug}/', {'departure_id': self.departure.pk})
        self.assertNotContains(response, 'booking-deposit-notice')

    def test_amount_and_activation_are_configurable_with_the_pack_minimum(self):
        self.tour.min_travelers = 5
        self.tour.deposit_amount = 875
        self.tour.save()
        booking = self.book(5)
        self.assertEqual(booking.deposit_required_amount, Decimal('875'))
        self.assertTrue(booking.deposit_pending)

    def test_deposit_is_part_of_total_and_snapshot_survives_tour_edits(self):
        booking = self.book(5)
        self.assertEqual(booking.total_price, Decimal('20000'))
        self.assertEqual(booking.deposit_required_amount, Decimal('500'))
        self.assertEqual(booking.workflow_stage, 'Awaiting deposit before approval')
        self.tour.deposit_amount = 900
        self.tour.save()
        booking.refresh_from_db()
        self.assertEqual(booking.deposit_required_amount, Decimal('500'))
        self.client.force_login(self.traveler)
        self.assertContains(self.client.get('/profile/reservations/'), 'You need to pay the deposit before')
        self.client.force_login(self.staff)
        self.client.post(f'/dashboard/reservation/{booking.pk}/validate/')
        self.client.post(f'/dashboard/reservation/{booking.pk}/paid/')
        booking.refresh_from_db()
        self.assertEqual((booking.status, booking.payment_status), ('pending', 'unpaid'))
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(f'/dashboard/reservation/{booking.pk}/deposit-received/')
        self.assertEqual(len(mail.outbox), 2)
        self.assertTrue(all('Deposit received' in message.subject for message in mail.outbox))
        self.assertTrue(all('Balance due: 19500.00 USD' in message.body for message in mail.outbox))
        booking.refresh_from_db()
        self.assertEqual(booking.deposit_received_by, self.staff)
        self.assertIsNotNone(booking.deposit_received_at)
        self.assertEqual(booking.balance_due, Decimal('19500'))
        self.assertEqual(booking.payment_status, 'unpaid')
        record_deposit_received(booking.pk, self.staff)
        self.assertEqual(BookingNotification.objects.filter(reservation=booking, event='deposit_received').count(), 2)
        self.client.post(f'/dashboard/reservation/{booking.pk}/validate/')
        self.client.post(f'/dashboard/reservation/{booking.pk}/paid/')
        booking.refresh_from_db()
        self.assertEqual((booking.status, booking.payment_status), ('booked', 'paid'))
        self.assertEqual(booking.balance_due, 0)

    def test_per_person_deposit_is_explicitly_configurable_and_staff_only(self):
        self.tour.deposit_per_person = True
        self.tour.save()
        booking = self.book(3)
        self.assertEqual(booking.deposit_required_amount, Decimal('1500'))
        with self.assertRaises(ValidationError):
            record_deposit_received(booking.pk, self.traveler)
        self.client.force_login(self.traveler)
        self.assertEqual(self.client.post(f'/dashboard/reservation/{booking.pk}/deposit-received/').status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(f'/dashboard/reservation/{booking.pk}/deposit-received/').status_code, 405)
