from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings

from .models import ContactEmailSettings, ContactMessage, Destination, Tour, Reservation, UserProfile


@override_settings(SECURE_SSL_REDIRECT=False, EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', DEFAULT_FROM_EMAIL='site@example.com')
class ContactDeliveryTests(TestCase):
    def setUp(self):
        ContactEmailSettings.objects.create(country='morocco', recipient_email='morocco@example.com')
        ContactEmailSettings.objects.create(country='ireland', recipient_email='ireland@example.com')
        self.payload = {'name': 'Alex', 'email': 'alex@example.com', 'subject': 'Rabat tour', 'message': 'Please send details.'}

    def test_recipient_is_editable_and_country_scoped(self):
        for country in ('morocco', 'ireland'):
            self.assertEqual(self.client.post(f'/{country}/contact/', self.payload).status_code, 302)
            self.assertEqual(mail.outbox[-1].to, [f'{country}@example.com'])
            self.assertEqual(mail.outbox[-1].reply_to, ['alex@example.com'])
            self.assertEqual(mail.outbox[-1].from_email, 'site@example.com')
        ContactEmailSettings.objects.filter(country='morocco').update(recipient_email='new@example.com')
        self.client.post('/morocco/contact/', self.payload)
        self.assertEqual(mail.outbox[-1].to, ['new@example.com'])

    def test_failed_delivery_and_missing_recipient_keep_enquiry(self):
        with patch('apps.core.contact_email.EmailMessage.send', side_effect=OSError('offline')):
            self.assertEqual(self.client.post('/morocco/contact/', self.payload).status_code, 302)
        ContactEmailSettings.objects.all().delete()
        self.assertEqual(self.client.post('/morocco/contact/', self.payload).status_code, 302)
        self.assertEqual(ContactMessage.objects.count(), 2)

    def test_invalid_email_is_not_sent_or_saved(self):
        self.payload['email'] = 'invalid'
        self.client.post('/morocco/contact/', self.payload)
        self.assertEqual(ContactMessage.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_admin_lists_only_own_country_recipient(self):
        staff = User.objects.create_superuser('staff', 'staff@example.com', 'test-password')
        self.client.force_login(staff)
        response = self.client.get('/admin/core/contactemailsettings/')
        self.assertContains(response, 'morocco@example.com')
        self.assertNotContains(response, 'ireland@example.com')
        other = ContactEmailSettings.objects.get(country='ireland')
        response = self.client.get(f'/admin/core/contactemailsettings/{other.pk}/change/')
        self.assertNotContains(response, 'ireland@example.com', status_code=302)

    def test_dashboard_uses_account_details_without_overwriting_other_guest(self):
        staff = User.objects.create_superuser('staff', 'staff@example.com', 'test-password')
        traveler = User.objects.create_user('traveler', first_name='Alex', last_name='Martin')
        UserProfile.objects.create(user=traveler, phone='+212600000001', country='morocco', postal_code='10000')
        tour = Tour.objects.create(title='Rabat', destination=Destination.objects.create(name='Rabat'), price_per_night=100)
        booking = Reservation.objects.create(user=traveler, tour=tour, start_date=date.today()+timedelta(days=10), end_date=date.today()+timedelta(days=11), total_price=200)
        self.client.force_login(staff)
        response = self.client.get('/morocco/dashboard/reservations/')
        self.assertContains(response, 'Alex Martin')
        self.assertContains(response, '+212600000001')
        self.assertContains(response, 'data-guest_full_name="Alex Martin"')
        booking.booking_for_other = True
        booking.guest_full_name = 'Other Guest'
        booking.guest_phone = '+212600000002'
        booking.save()
        response = self.client.get('/morocco/dashboard/reservations/')
        self.assertContains(response, 'data-guest_full_name="Other Guest"')
        self.assertContains(response, 'data-guest_phone="+212600000002"')
        self.assertContains(response, 'data-account_name="Alex Martin"')
        UserProfile.objects.all().delete()
        self.assertContains(self.client.get('/morocco/dashboard/reservations/'), 'Not provided')
