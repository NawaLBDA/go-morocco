from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch, Mock

from django.contrib.auth.models import User
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.db import transaction

from .models import BookingNotificationSettings, BookingNotification, Tour, Destination, Reservation
from .assistant_service import stream_answer
from apps.reservations.notifications import deliver_notification


@override_settings(SECURE_SSL_REDIRECT=False, EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   DEFAULT_FROM_EMAIL='site@example.com')
class ServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('traveler', first_name='Alex', email='alex@example.com')
        self.tour = Tour.objects.create(title='Rabat', destination=Destination.objects.create(name='Rabat'), price_per_night=100)

    def book(self):
        return Reservation.objects.create(user=self.user, tour=self.tour,
            start_date=date.today()+timedelta(days=90), end_date=date.today()+timedelta(days=91), total_price=200)

    def test_notifications_multiple_staff_recipients_once_after_commit(self):
        BookingNotificationSettings.objects.create(country='morocco', email_recipients='one@example.com\ntwo@example.com\none@example.com')
        BookingNotificationSettings.objects.create(country='ireland', email_recipients='ireland@example.com')
        with self.captureOnCommitCallbacks(execute=True):
            booking = self.book()
            self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(len(mail.outbox), 4)
        self.assertEqual({message.to[0] for message in mail.outbox}, {'one@example.com', 'two@example.com', 'alex@example.com', 'contact@culturehoptours.com'})
        self.assertIn('Rabat', mail.outbox[0].body)
        with self.captureOnCommitCallbacks(execute=True):
            booking.admin_note = 'Edited'
            booking.save()
        self.assertEqual(len(mail.outbox), 4)
        for notice in booking.notifications.all():
            deliver_notification(notice.pk)
        self.assertEqual(len(mail.outbox), 4)

    def test_rollback_sends_nothing(self):
        BookingNotificationSettings.objects.create(country='morocco', email_recipients='one@example.com')
        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    self.book()
                    raise RuntimeError('rollback')
            except RuntimeError:
                pass
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(BookingNotification.objects.count(), 0)

    def test_failure_keeps_booking_and_can_be_retried(self):
        BookingNotificationSettings.objects.create(country='morocco', email_recipients='one@example.com')
        with patch('apps.reservations.notifications.EmailMessage.send', side_effect=OSError('offline')):
            with self.captureOnCommitCallbacks(execute=True):
                booking = self.book()
        notice = booking.notifications.get(recipient='one@example.com', audience='staff')
        self.assertEqual(notice.status, 'failed')
        self.assertTrue(Reservation.objects.filter(pk=booking.pk).exists())
        deliver_notification(notice.pk)
        notice.refresh_from_db()
        self.assertEqual(notice.status, 'sent')

    @override_settings(TWILIO_ACCOUNT_SID='test', TWILIO_AUTH_TOKEN='secret', TWILIO_WHATSAPP_FROM='whatsapp:+12345678901')
    def test_whatsapp_template_and_multiple_numbers(self):
        BookingNotificationSettings.objects.create(country='morocco', whatsapp_recipients='+212600000001\n+212600000002', whatsapp_content_sid='HX'+'a'*32)
        with patch('twilio.rest.Client') as client:
            client.return_value.messages.create.return_value.sid = 'SMtest'
            with self.captureOnCommitCallbacks(execute=True):
                self.book()
            self.assertEqual(client.return_value.messages.create.call_count, 2)
            kwargs = client.return_value.messages.create.call_args.kwargs
            self.assertEqual(kwargs['content_sid'], 'HX'+'a'*32)
            self.assertIn('Rabat', kwargs['content_variables'])

    def test_notification_settings_validation(self):
        config = BookingNotificationSettings(email_recipients='invalid')
        with self.assertRaises(ValidationError):
            config.full_clean()
        config.email_recipients = ''
        config.whatsapp_recipients = '0600000000'
        with self.assertRaises(ValidationError):
            config.full_clean()

    def test_registration_name_never_grants_admin(self):
        user = User.objects.create_user('admin-tourist')
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_admin_simplified_and_contact_is_help_only(self):
        staff = User.objects.create_superuser('staff', 'staff@example.com', 'test-password')
        self.client.force_login(staff)
        response = self.client.get('/admin/')
        self.assertNotContains(response, '/admin/core/section/')
        self.assertNotContains(response, '/admin/core/countrycontent/')
        response = self.client.get('/admin/core/tour/add/')
        self.assertNotContains(response, 'Transport and accommodation')
        self.assertNotContains(response, 'name="transport"')
        response = self.client.get('/morocco/contact/')
        self.assertNotContains(response, 'Quote / Question / Booking')
        self.assertContains(response, 'How can we help you?')
        self.assertNotContains(response, 'For questions, quotes, or bookings')

    @override_settings(RESEND_API_KEY='test-secret')
    def test_https_email_backend_payload_and_failure(self):
        from .email_backend import ResendEmailBackend
        from django.core.mail import EmailMessage
        message = EmailMessage('Test', 'Message', 'site@example.com', ['staff@example.com'], reply_to=['guest@example.com'])
        with patch('apps.core.email_backend.requests.post') as post:
            post.return_value.status_code = 200
            self.assertEqual(ResendEmailBackend().send_messages([message]), 1)
            self.assertEqual(post.call_args.kwargs['json']['reply_to'], ['guest@example.com'])
            post.return_value.status_code = 401
            with self.assertRaises(RuntimeError):
                ResendEmailBackend().send_messages([message])

    def test_notification_admin_is_country_scoped(self):
        booking = self.book()
        notice = BookingNotification.objects.create(reservation=booking, channel='email', recipient='private@example.com')
        staff = User.objects.create_superuser('staff', 'staff@example.com', 'test-password')
        self.client.force_login(staff)
        self.assertContains(self.client.get('/admin/core/bookingnotification/'), 'private@example.com')
        self.assertNotContains(self.client.get('/admin/core/bookingnotification/', {'reservation__tour__country': 'ireland'}), 'private@example.com')

    @override_settings(HF_API_TOKEN='', OPENAI_API_KEY='')
    def test_chat_endpoints_degrade_to_real_tours_without_provider(self):
        self.client.force_login(self.user)
        payload = {'message': 'Could you explain the local culture in detail?'}
        response = self.client.post('/morocco/api/ai-chat-stream/', payload, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        content = b''.join(response.streaming_content).decode()
        self.assertIn('temporarily unavailable', content)
        self.assertIn('Rabat', content)
        response = self.client.post('/morocco/api/ai-chat/', payload, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('temporarily unavailable', response.json()['reply'])


@override_settings(HF_API_TOKEN='test-hf', HF_MODEL='configured-model', HF_FALLBACK_MODEL='', OPENAI_API_KEY='test-openai', OPENAI_MODEL='configured-model')
class AssistantFallbackTests(TestCase):
    def test_hf_failure_uses_configured_openai(self):
        event = SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='Hello'))])
        with patch('apps.core.views._hf_router_chat_completion_stream', side_effect=RuntimeError('provider unavailable')):
            with patch('apps.core.assistant_service.openai.OpenAI') as client:
                client.return_value.chat.completions.create.return_value = [event]
                self.assertEqual(''.join(stream_answer('Help tourists', 'Hello')), 'Hello')

    def test_all_providers_failed(self):
        with patch('apps.core.views._hf_router_chat_completion_stream', side_effect=RuntimeError('failed')):
            with patch('apps.core.assistant_service.openai.OpenAI', side_effect=RuntimeError('failed')):
                with self.assertRaises(RuntimeError):
                    list(stream_answer('Help tourists', 'Hello'))

    def test_partial_answer_is_not_replaced_by_another_provider(self):
        def tokens(*args, **kwargs):
            yield 'First part'
            raise RuntimeError('interrupted')
        with patch('apps.core.views._hf_router_chat_completion_stream', tokens):
            with patch('apps.core.assistant_service.openai.OpenAI') as client:
                result = ''.join(stream_answer('Help tourists', 'Hello'))
                self.assertIn('First part', result)
                self.assertIn('interrupted', result)
                client.assert_not_called()
