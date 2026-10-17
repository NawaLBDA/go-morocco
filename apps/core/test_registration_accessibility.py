from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from .models import UserProfile, Destination, Tour, Reservation


@override_settings(SECURE_SSL_REDIRECT=False)
class RegistrationAccessibilityTests(TestCase):
    def payload(self, username, deaf=False):
        data = dict(username=username, full_name='Alex Martin', email='alex@example.com',
                    phone='+212600000001', country='morocco', postal_code='10000',
                    password1='Travel-test-9182!', password2='Travel-test-9182!')
        if deaf:
            data['is_deaf'] = 'on'
        return data

    def test_optional_status_is_saved_checked_or_unchecked(self):
        for username, deaf in [('deaf-traveler', True), ('other-traveler', False)]:
            response = self.client.post('/morocco/register/', self.payload(username, deaf))
            self.assertEqual(response.status_code, 302)
            self.assertEqual(UserProfile.objects.get(user__username=username).is_deaf, deaf)

    def test_checkbox_is_retained_after_invalid_registration(self):
        data = self.payload('traveler', True)
        data['password2'] = 'different'
        response = self.client.post('/morocco/register/', data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="form-check-input" checked')
        self.assertFalse(User.objects.filter(username='traveler').exists())

    def test_admin_sees_account_status_even_for_another_guest(self):
        self.client.post('/morocco/register/', self.payload('traveler', True))
        user = User.objects.get(username='traveler')
        tour = Tour.objects.create(title='Rabat', destination=Destination.objects.create(name='Rabat'), price_per_night=100)
        Reservation.objects.create(user=user, tour=tour, start_date=date.today()+timedelta(days=20),
            end_date=date.today()+timedelta(days=21), total_price=200, booking_for_other=True, guest_full_name='Other Guest')
        staff = User.objects.create_superuser('staff', 'staff@example.com', 'test-password')
        self.client.force_login(staff)
        response = self.client.get('/morocco/dashboard/reservations/')
        self.assertContains(response, 'Deaf (account holder)')
        self.assertContains(response, 'data-account_deaf="Yes"')
        profile = user.profile
        profile.is_deaf = False
        profile.save()
        self.assertContains(self.client.get('/morocco/dashboard/reservations/'), 'data-account_deaf="No"')
        self.client.logout()
        self.assertEqual(self.client.get('/morocco/dashboard/reservations/').status_code, 302)
