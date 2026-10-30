from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone
from .models import Country, Destination, Tour, TourDeparture, Promotion, UserProfile, SiteSettings
from .catalogue import tour_rate
from apps.reservations.views import _create_pending_reservation, _recalculate_total_for_reservation


@override_settings(SECURE_SSL_REDIRECT=False)
class GlobalSiteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('global-traveler')
        self.tour = Tour.objects.create(title='Atlas journey', price_per_night=100,
            destination=Destination.objects.create(name='Atlas'))
        self.day = date.today() + timedelta(days=60)
        self.departure = TourDeparture.objects.create(tour=self.tour, start_date=self.day,
            end_date=self.day + timedelta(days=2), is_published=True, max_participants=4)

    def book(self, tour=None, departure=None, persons=1):
        tour, departure = tour or self.tour, departure or self.departure
        return _create_pending_reservation(user=self.user, tour=tour, start_date=departure.start_date,
            end_date=departure.end_date, departure_id=departure.pk, persons=persons,
            payment_method='cash', full_package=False, include_transport=False,
            include_hotel=False, extra_activity_ids=[])

    def test_new_country_works_without_code_and_has_independent_calendar(self):
        Country.objects.create(slug='japan', name='Japan', is_active=True)
        tour = Tour.objects.create(title='Kyoto discovery', country='japan', price_per_night=120,
            destination=Destination.objects.create(name='Kyoto', country='japan'))
        departure = TourDeparture.objects.create(tour=tour, start_date=self.day,
            end_date=self.day + timedelta(days=2), is_published=True)
        self.assertEqual(self.book()[3], 200)
        self.assertEqual(self.book(tour, departure)[3], 200)
        response = self.client.get('/', {'country': 'japan'})
        self.assertContains(response, 'Kyoto discovery')
        self.assertNotContains(response, 'Atlas journey')
        self.assertEqual(self.client.get('/tour/' + tour.slug + '/').status_code, 200)

    def test_monthly_calendar_filters_and_drafts(self):
        response = self.client.get('/')
        self.assertEqual(response.context['departure_groups'][0][0], self.day.replace(day=1))
        self.departure.is_published = False
        self.departure.save()
        self.assertEqual(self.client.get('/').context['departure_groups'], [])
        self.assertEqual(self.client.get('/', {'country': 'missing'}).status_code, 404)

    def test_home_groups_countries_and_shows_one_card_per_date_without_undated_fallback(self):
        second = TourDeparture.objects.create(tour=self.tour, start_date=self.day + timedelta(days=10),
            end_date=self.day + timedelta(days=12), is_published=True)
        response = self.client.get('/')
        self.assertContains(response, 'class="country-pack"')
        self.assertNotContains(response, 'View &amp; book this journey')
        response = self.client.get('/', {'country': 'morocco'})
        self.assertContains(response, 'View &amp; book this journey', count=2)
        self.assertContains(response, '?departure_id=' + str(second.pk))
        self.assertContains(response, 'fa-regular fa-calendar')
        self.assertContains(response, '3 days')
        self.assertContains(response, 'class="collection-navigation', count=1)
        self.assertNotContains(response, 'journey-search')
        self.tour.departures.update(is_published=False)
        response = self.client.get('/', {'country': 'morocco'})
        self.assertNotContains(response, self.tour.title)

    def test_country_link_and_cross_country_destination_validation(self):
        self.assertEqual(self.tour.region_id, 'morocco')
        self.tour.country = 'ireland'
        with self.assertRaises(ValidationError):
            self.tour.full_clean()
        with self.assertRaises(ValidationError):
            Destination(name='Unknown', country='missing').full_clean()

    def test_deaf_package_cannot_be_opened_or_booked_without_status(self):
        self.tour.deaf_only = True
        self.tour.save()
        self.assertNotContains(self.client.get('/'), 'Atlas journey')
        self.assertEqual(self.client.get('/tour/' + self.tour.slug + '/').status_code, 200)
        self.assertContains(self.client.get('/', {'country': 'morocco'}), 'Deaf travelers only')
        UserProfile.objects.create(user=self.user, is_deaf=True, phone='123', country='France', postal_code='123')
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/tour/' + self.tour.slug + '/').status_code, 200)
        self.assertEqual(self.book()[3], 200)

    def test_capacity_is_enforced_on_server(self):
        self.assertEqual(self.book(persons=5)[3], 400)
        booking, _, _, _ = self.book()
        booking.num_persons = 5
        with self.assertRaises(ValidationError):
            booking.save()

    def test_group_discount_starts_above_five_people(self):
        options = dict(tour=self.tour, start_date=self.day, end_date=self.day + timedelta(days=1),
            full_package=False, include_transport=False, include_hotel=False, selected_extra_activities=[])
        self.assertEqual(_recalculate_total_for_reservation(persons=5, **options)[0], Decimal('500.00'))
        self.assertEqual(_recalculate_total_for_reservation(persons=6, **options)[0], Decimal('540.00'))

    def test_full_discount_is_rendered_and_charged_as_zero(self):
        self.tour.is_promotion, self.tour.discount_percent = True, 100
        self.tour.save()
        response = self.client.get('/tour/' + self.tour.slug + '/', {'departure_id': self.departure.pk})
        self.assertContains(response, 'id="base-price" value="0.00"')
        self.assertEqual(self.book()[0].total_price, Decimal('0.00'))

    def test_dated_promotion_changes_actual_booking_rate(self):
        today = timezone.localdate()
        Promotion.objects.create(name='Christmas', percent=40, country='morocco', active=True,
            apply_to_all=True, christmas=True, starts_on=today, ends_on=today)
        self.assertEqual(tour_rate(self.tour), Decimal('60.00'))
        booking, _, _, status = self.book()
        self.assertEqual(status, 200)
        self.assertEqual(booking.total_price, Decimal('180.00'))
        self.assertTrue(self.client.get('/').context['festive_theme'])
        Promotion.objects.update(ends_on=today - timedelta(days=1))
        self.assertEqual(tour_rate(self.tour), Decimal('100.00'))

    def test_global_admin_lists_all_countries_and_global_settings(self):
        staff = User.objects.create_superuser('manager', 'manager@example.com', 'test')
        self.client.force_login(staff)
        self.assertEqual(self.client.get('/admin/core/country/').status_code, 200)
        self.client.post('/admin/workspace/select/', {'country': 'morocco'})
        self.assertEqual(self.client.get('/admin/core/tour/add/').status_code, 200)
        self.assertRedirects(self.client.get('/ireland-admin/'), '/admin/')

    def test_custom_home_title_is_used_without_a_hero_photo(self):
        SiteSettings.objects.update_or_create(pk=1, defaults={'hero_title': 'Our custom headline', 'hero_image': 'img/site/custom.jpg'})
        self.assertContains(self.client.get('/'), 'Our custom headline')
        self.assertNotContains(self.client.get('/'), 'img/site/custom.jpg')
        self.assertContains(self.client.get('/'), 'home-title-bar')
