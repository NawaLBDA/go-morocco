from datetime import timedelta
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from .models import UserProfile, Tour, TourDeparture, Destination, Reservation
from apps.reservations.views import _create_pending_reservation


@override_settings(SECURE_SSL_REDIRECT=False, EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class TravelerAccountTests(TestCase):
    def setUp(self):
        self.deaf = User.objects.create_user('deaf-traveler', email='deaf@example.com', password='Initial-travel-123!', first_name='Alex')
        self.other = User.objects.create_user('other-traveler', email='other@example.com', password='Initial-travel-123!')
        self.profile = UserProfile.objects.create(user=self.deaf, is_deaf=True, phone='123', country='France', postal_code='75000')
        UserProfile.objects.create(user=self.other, is_deaf=False, phone='456', country='Ireland', postal_code='D01')
        self.tour = Tour.objects.create(title='Rabat dates', destination=Destination.objects.create(name='Rabat'), price_per_night=100)
        start = timezone.localdate()+timedelta(days=50)
        self.restricted = TourDeparture.objects.create(tour=self.tour, start_date=start, end_date=start+timedelta(days=2), deaf_only=True, is_published=True)
        self.public = TourDeparture.objects.create(tour=self.tour, start_date=start+timedelta(days=10), end_date=start+timedelta(days=12), is_published=True)

    def book(self, user, departure=None):
        dep=departure or self.restricted
        return _create_pending_reservation(user=user, tour=self.tour, start_date=dep.start_date, end_date=dep.end_date,
            departure_id=dep.pk, persons=2, payment_method='cash', full_package=False, include_transport=False, include_hotel=False, extra_activity_ids=[])

    def test_deaf_labeled_departure_accepts_a_non_deaf_account(self):
        self.assertEqual(self.book(self.other)[3], 200)
        self.assertEqual(self.book(self.deaf, self.public)[3], 200)
        response=self.client.get('/', {'country':'morocco'})
        self.assertContains(response, 'For deaf travelers · Everyone welcome', count=1)
        self.assertContains(response, 'deaf-travelers.svg')

    def test_public_and_non_deaf_visitors_see_the_normal_booking_form(self):
        url=f'/tour/{self.tour.slug}/?departure_id={self.restricted.pk}'
        self.assertContains(self.client.get(url),'id="booking-form"')
        self.client.force_login(self.other)
        response=self.client.get(url)
        self.assertContains(response,'id="booking-form"')
        self.assertNotContains(response,'Your account is not eligible')
        response=self.client.post(f'/tour/{self.tour.pk}/book/', {'departure_id':self.restricted.pk,
            'start_date':self.restricted.start_date,'end_date':self.restricted.end_date,'persons':1,'payment_method':'cash'})
        self.assertRedirects(response,'/profile/reservations/')
        self.assertEqual(Reservation.objects.get().user,self.other)

    def test_tour_label_also_accepts_everyone_and_keeps_waitlist_open(self):
        self.tour.deaf_only=True
        self.tour.save()
        self.assertEqual(self.book(self.other,self.public)[3],200)
        self.assertEqual(self.book(self.deaf)[3],200)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(f'/departure/{self.restricted.pk}/waitlist/', {'persons':1,'email':'other@example.com'}).status_code,302)
        from .models import WaitlistEntry
        self.assertTrue(WaitlistEntry.objects.filter(user=self.other).exists())

    def test_profile_and_reservations_are_private_read_only_and_user_scoped(self):
        self.assertEqual(self.client.get('/profile/').status_code,302)
        self.assertEqual(self.client.get('/profile/reservations/').status_code,302)
        own=self.book(self.deaf)[0]
        self.book(self.other,self.public)
        self.client.force_login(self.deaf)
        response=self.client.get('/profile/')
        self.assertContains(response,'deaf@example.com')
        self.assertContains(response,'France')
        self.assertNotContains(response,'name="is_deaf"')
        self.assertEqual(self.client.post('/profile/',{'is_deaf':'','email':'changed@example.com'}).status_code,405)
        self.profile.refresh_from_db();self.deaf.refresh_from_db()
        self.assertTrue(self.profile.is_deaf)
        self.assertEqual(self.deaf.email,'deaf@example.com')
        response=self.client.get('/profile/reservations/')
        self.assertEqual(list(response.context['bookings']),[own])
        self.assertNotContains(response,'<form')
        self.assertEqual(self.client.post('/profile/reservations/',{'id':own.pk,'status':'cancelled'}).status_code,405)
        page=self.client.get(f'/tour/{self.tour.slug}/?departure_id={self.restricted.pk}')
        self.assertContains(page,'View my reservations')
        self.assertNotContains(page,'Your reservation details will appear here')
        self.assertNotContains(page,'reservation-overview-grid')

    def test_password_changes_only_after_email_link_and_token_is_single_use(self):
        response=self.client.post('/account/password/reset/',{'email':self.deaf.email})
        self.assertEqual(response.status_code,302)
        self.assertEqual(len(mail.outbox),1)
        self.assertEqual(mail.outbox[0].to,[self.deaf.email])
        self.assertTrue(mail.outbox[0].alternatives)
        self.deaf.refresh_from_db();self.assertTrue(self.deaf.check_password('Initial-travel-123!'))
        uid=urlsafe_base64_encode(force_bytes(self.deaf.pk));token=default_token_generator.make_token(self.deaf)
        url=f'/account/password/reset/{uid}/{token}/'
        response=self.client.get(url)
        self.assertEqual(response.status_code,302)
        response=self.client.post(response.url,{'new_password1':'New-travel-456!','new_password2':'New-travel-456!'})
        self.assertEqual(response.status_code,302)
        self.deaf.refresh_from_db();self.assertTrue(self.deaf.check_password('New-travel-456!'))
        self.assertFalse(default_token_generator.check_token(self.deaf,token))
        self.profile.refresh_from_db();self.assertTrue(self.profile.is_deaf)
