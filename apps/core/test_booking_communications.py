from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth.models import User, AnonymousUser
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from .forms import TravelerRegistrationForm
from .models import Tour, Destination, Reservation, ContactEmailSettings, SiteSettings, HomeHero, Country
from apps.reservations.notifications import deliver_notification
from apps.reservations.views import _create_pending_reservation


@override_settings(SECURE_SSL_REDIRECT=False, EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', DEFAULT_FROM_EMAIL='sender@example.com')
class BookingCommunicationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('traveler-mail', email='traveler@example.com', first_name='Alex')
        self.tour = Tour.objects.create(title='Rabat journey', destination=Destination.objects.create(name='Rabat'), price_per_night=100)
        ContactEmailSettings.objects.create(country='morocco', recipient_email='contact@example.com')
        SiteSettings.objects.update_or_create(pk=1, defaults={'booking_email':'bookings@example.com'})

    def book(self):
        start = timezone.localdate()+timedelta(days=90)
        return Reservation.objects.create(user=self.user, tour=self.tour, start_date=start, end_date=start+timedelta(days=2), total_price=300, payment_method='transfer')

    def test_three_events_notify_customer_and_booking_inbox_once_with_html(self):
        with self.captureOnCommitCallbacks(execute=True):
            booking = self.book()
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual({m.to[0] for m in mail.outbox}, {'traveler@example.com', 'bookings@example.com'})
        customer = next(m for m in mail.outbox if m.to == ['traveler@example.com'])
        self.assertIn('pending approval', customer.body)
        self.assertEqual(customer.reply_to, ['bookings@example.com'])
        self.assertEqual(customer.alternatives[0][1], 'text/html')
        self.assertIn('Rabat journey', customer.alternatives[0][0])
        with self.captureOnCommitCallbacks(execute=True):
            booking.status = 'booked'
            booking.save()
        self.assertEqual(len(mail.outbox), 4)
        self.assertIn('approved', mail.outbox[-2].body)
        self.assertNotIn('Payment recorded:', mail.outbox[-2].body)
        with self.captureOnCommitCallbacks(execute=True):
            booking.payment_status = 'paid'
            booking.save()
            booking.admin_note = 'Updated'
            booking.save()
        self.assertEqual(len(mail.outbox), 6)
        self.assertIn('Payment recorded: 300', mail.outbox[-2].body)
        for notice in booking.notifications.all():
            deliver_notification(notice.pk)
        self.assertEqual(len(mail.outbox), 6)

    def test_professional_sender_can_be_set_later_and_failure_is_retryable(self):
        SiteSettings.objects.update_or_create(pk=1, defaults={'sender_email': 'journeys@example.com'})
        with patch('apps.reservations.notifications.EmailMessage.send', side_effect=OSError('offline')):
            with self.captureOnCommitCallbacks(execute=True):
                booking = self.book()
        notice = booking.notifications.get(audience='traveler')
        self.assertEqual(notice.status, 'failed')
        self.assertEqual(Reservation.objects.count(), 1)
        deliver_notification(notice.pk)
        self.assertIn('journeys@example.com', mail.outbox[-1].from_email)
        self.assertIn('Culture Hop Tours', mail.outbox[-1].from_email)

    def test_registration_rejects_missing_and_invalid_email_on_server(self):
        data = {'username': 'new-person', 'password1': 'Strong-pass-2468!', 'password2': 'Strong-pass-2468!', 'full_name': 'Alex Traveler'}
        for email in ['', 'invalid-email']:
            form = TravelerRegistrationForm({**data, 'email': email})
            self.assertFalse(form.is_valid())
            self.assertIn('email', form.errors)
            response = self.client.post('/register/', {**data, 'email': email})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(User.objects.filter(username='new-person').exists())
        self.assertTrue(TravelerRegistrationForm({**data, 'email': 'alex@example.com'}).is_valid())
        response = self.client.post('/register/', {**data, 'email': 'alex@example.com',
            'phone': '+212600000000', 'country': 'Morocco', 'postal_code': '10000',
            'next': '/tour/rabat/?departure_id=4'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('next=', response.url)
        self.assertEqual(User.objects.get(username='new-person').email, 'alex@example.com')

    def test_anonymous_booking_cannot_create_a_reservation(self):
        response = self.client.post(f'/tour/{self.tour.pk}/book/', {})
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)
        result = _create_pending_reservation(user=AnonymousUser(), tour=self.tour)
        self.assertEqual(result[3], 401)
        self.assertFalse(Reservation.objects.exists())

    @override_settings(STRIPE_WEBHOOK_SECRET='test-secret')
    def test_unsigned_payment_webhook_is_rejected(self):
        from django.test import RequestFactory
        from apps.reservations.views import stripe_webhook
        response = stripe_webhook(RequestFactory().post('/webhook/', data='{"type":"payment_intent.succeeded"}', content_type='application/json'))
        self.assertEqual(response.status_code, 400)

    def test_stored_hero_slides_do_not_render_in_the_compact_home_header(self):
        from django.core.management import call_command
        from io import StringIO
        call_command('seed_home_heroes', stdout=StringIO())
        self.assertEqual(HomeHero.objects.count(), 2)
        self.assertFalse(Country.objects.get(slug='nigeria').is_active)
        response = self.client.get('/')
        self.assertNotContains(response, 'hero-carousel')
        self.assertContains(response, 'home-title-bar')
        self.assertNotContains(response, 'data-hero-pause')
        self.assertNotContains(response, 'data-hero-next')
        self.assertNotContains(response, 'nigeria-hero.webp')
        self.assertNotContains(response, '?country=nigeria#journeys')
        hero = HomeHero.objects.get(starter_image='nigeria')
        hero.title = 'Team edited headline'
        hero.save()
        call_command('seed_home_heroes', stdout=StringIO())
        hero.refresh_from_db()
        self.assertEqual(hero.title, 'Team edited headline')
