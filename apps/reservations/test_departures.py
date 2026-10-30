from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from apps.core.models import Destination, Tour, TourActivity, TourDeparture, Reservation
from apps.core.views import _build_itinerary_days
from apps.core.admin import DepartureDayForm, DepartureDayFormSet, TourDepartureFormSet
from django.forms.models import inlineformset_factory
from apps.core.models import DepartureDay
from .views import _create_pending_reservation


@override_settings(SECURE_SSL_REDIRECT=False)
class ScheduledDepartureTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('scheduled-traveler', password='test-password')
        self.tour = Tour.objects.create(title='Rabat', destination=Destination.objects.create(name='Rabat'), price_per_night=100)
        self.day = date.today() + timedelta(days=50)
        self.departure = TourDeparture.objects.create(tour=self.tour, start_date=self.day,
            end_date=self.day + timedelta(days=4), is_published=True)

    def book(self, departure=None, **changes):
        departure = departure or self.departure
        args = dict(user=self.user, tour=self.tour, departure_id=departure.pk,
            start_date=departure.start_date, end_date=departure.end_date, persons=1,
            payment_method='cash', full_package=False, include_transport=False,
            include_hotel=False, extra_activity_ids=[])
        args.update(changes)
        return _create_pending_reservation(**args)

    def test_morocco_accepts_bank_transfer_and_rejects_card(self):
        reservation, error, _, status = self.book(payment_method='card')
        self.assertIsNone(reservation)
        self.assertEqual(status, 400)
        reservation, error, _, status = self.book(payment_method='transfer')
        self.assertIsNone(error)
        self.assertEqual(reservation.payment_method, 'transfer')
        self.assertEqual(reservation.payment_status, 'unpaid')

    def test_default_fourteen_days_and_legacy_configurable_nineteen(self):
        self.assertEqual(self.tour.max_days, 14)
        self.departure.full_clean()
        longer = TourDeparture(tour=self.tour, start_date=self.day, end_date=self.day + timedelta(days=18))
        with self.assertRaises(ValidationError):
            longer.full_clean()
        self.tour.max_days = 19
        self.tour.save()
        longer.full_clean()
        longer.is_published = True
        longer.save()
        reservation, error, _, _ = self.book(longer)
        self.assertIsNone(error)
        self.assertEqual(reservation.duration_days, 19)
        self.assertEqual(reservation.total_price, 1900)

    def test_one_day_departure_is_bookable_and_charged_once(self):
        single = TourDeparture.objects.create(tour=self.tour, start_date=self.day, end_date=self.day, is_published=True)
        reservation, error, _, status = self.book(single)
        self.assertEqual(status, 200)
        self.assertIsNone(error)
        self.assertEqual(reservation.duration_days, 1)
        self.assertEqual(reservation.total_price, 100)
        self.assertEqual(self.book(single)[3], 409)

    def test_removed_day_changes_programme_and_total_but_keeps_calendar_blocked(self):
        first = TourActivity.objects.create(tour=self.tour, title='Kasbah visit')
        removed = TourActivity.objects.create(tour=self.tour, title='Removed museum visit', day_number=2)
        day1 = self.departure.program_days.get(day_number=1)
        day1.activities.add(first)
        day2 = self.departure.program_days.get(day_number=2)
        day2.activities.add(removed)
        day2.is_visible = False
        day2.save()
        itinerary = _build_itinerary_days(self.tour, departure=self.departure)
        self.assertEqual(len(itinerary), 4)
        self.assertNotIn(2, [day['day_number'] for day in itinerary])
        self.assertNotIn('Removed museum visit', str(itinerary))
        reservation, error, _, _ = self.book(persons=6)
        self.assertIsNone(error)
        self.assertEqual(reservation.duration_days, 4)
        self.assertEqual(reservation.total_price, Decimal('2160'))
        other = Tour.objects.create(title='Marrakech', destination=self.tour.destination, price_per_night=70)
        overlap = TourDeparture.objects.create(tour=other, start_date=self.day + timedelta(days=1),
            end_date=self.day + timedelta(days=1), is_published=True)
        self.assertEqual(self.book(overlap, tour=other)[3], 409)

    def test_draft_foreign_and_arbitrary_dates_cannot_be_booked(self):
        self.assertEqual(self.book(start_date=self.day + timedelta(days=1))[3], 409)
        self.assertEqual(self.book(departure_id=999999)[3], 409)
        self.departure.is_published = False
        self.departure.save()
        self.assertEqual(self.book()[3], 409)
        self.assertFalse(Reservation.objects.exists())

    def test_no_active_days_cannot_be_booked(self):
        self.departure.program_days.update(is_visible=False)
        self.assertEqual(self.book()[3], 409)

    def test_existing_booking_days_and_prices_are_not_recomputed_from_programme(self):
        reservation, _, _, _ = self.book()
        self.departure.program_days.filter(day_number=1).update(is_visible=False)
        reservation.refresh_from_db()
        self.assertEqual(reservation.duration_days, 5)
        self.assertEqual(reservation.total_price, 500)

    def test_legacy_reservation_keeps_its_original_duration_and_price(self):
        reservation = Reservation.objects.create(user=self.user, tour=self.tour,
            start_date=self.day, end_date=self.day + timedelta(days=2), total_price=200)
        self.assertEqual(reservation.duration_days, 2)
        self.assertEqual(reservation.total_price, 200)

    def test_reserved_departure_dates_cannot_be_changed(self):
        self.book()
        self.departure.end_date -= timedelta(days=1)
        with self.assertRaises(ValidationError):
            self.departure.full_clean()

    def test_departure_day_form_rejects_other_tour_activity(self):
        other = Tour.objects.create(title='Other', destination=self.tour.destination, price_per_night=10)
        activity = TourActivity.objects.create(tour=other, title='Wrong tour')
        day = self.departure.program_days.first()
        form = DepartureDayForm(data={'departure': self.departure.pk, 'day_number': 1, 'is_visible': True,
            'activities': [activity.pk]}, instance=day)
        self.assertFalse(form.is_valid())
        self.assertIn('activities', form.errors)

    def test_page_uses_departures_and_only_the_selected_programme(self):
        path = '/morocco/tour/' + self.tour.slug + '/'
        response = self.client.get(path)
        self.assertNotContains(response, 'id="departure-choice"')
        self.assertNotContains(response, 'id="booking-form"')
        self.assertContains(response, 'View dates &amp; availability')
        self.assertNotContains(response, 'https://js.stripe.com/v3/')
        self.assertNotContains(response, 'Unavailable dates across all Morocco tours')
        self.assertNotContains(response, 'Maximum allowed duration')
        self.assertNotContains(response, 'Nights')
        self.assertEqual(response.context['itinerary_days'], [])
        response = self.client.get(path, {'departure_id': self.departure.pk})
        self.assertContains(response, 'type="hidden" name="departure_id" value="' + str(self.departure.pk) + '"')
        self.assertContains(response, 'class="fixed-departure')
        self.assertContains(response, 'Bank transfer')
        self.assertNotContains(response, 'id="departure-choice"')
        self.assertEqual(len(response.context['itinerary_days']), 5)
        self.assertEqual(response.context['selected_departure'], self.departure)

    def test_invalid_departure_cannot_silently_change_booking_dates(self):
        path = '/tour/' + self.tour.slug + '/'
        self.assertEqual(self.client.get(path, {'departure_id': '999999'}).status_code, 404)
        self.assertEqual(self.client.get(path, {'departure_id': 'invalid'}).status_code, 404)

    def test_web_submission_uses_published_departure_and_server_price(self):
        self.client.force_login(self.user)
        response = self.client.post(f'/morocco/tour/{self.tour.pk}/book/', {
            'departure_id': self.departure.pk, 'start_date': self.day.isoformat(),
            'end_date': self.departure.end_date.isoformat(), 'persons': 2, 'payment_method': 'cash', 'total_price': 1})
        self.assertEqual(response.status_code, 302)
        reservation = Reservation.objects.get()
        self.assertEqual(reservation.departure, self.departure)
        self.assertEqual(reservation.total_price, 1000)
        self.assertEqual(reservation.status, 'pending')

    def test_traveler_can_choose_another_non_overlapping_departure_of_same_tour(self):
        self.book()
        self.client.force_login(self.user)
        later = TourDeparture.objects.create(tour=self.tour, start_date=self.day + timedelta(days=20),
            end_date=self.day + timedelta(days=20), is_published=True)
        response = self.client.get('/morocco/tour/' + self.tour.slug + '/', {'departure_id': later.pk})
        self.assertIsNone(response.context['reservation'])
        self.assertContains(response, 'id="booking-form"')
        self.assertEqual(response.context['selected_departure'], later)
        self.assertEqual(self.book(later)[3], 200)
        self.assertEqual(Reservation.objects.filter(status='pending').count(), 2)

    def test_availability_rejects_wrong_departure_and_allows_one_day(self):
        query = {'departure_id': self.departure.pk, 'tour_id': self.tour.pk,
                 'start_date': self.day.isoformat(), 'end_date': self.departure.end_date.isoformat()}
        response = self.client.get('/morocco/api/guide-availability/', query)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['days'], 5)
        query['end_date'] = self.day.isoformat()
        self.assertEqual(self.client.get('/morocco/api/guide-availability/', query).status_code, 400)

    def test_admin_cannot_publish_empty_programme_or_change_reserved_programme(self):
        FormSet = inlineformset_factory(TourDeparture, DepartureDay, form=DepartureDayForm,
            formset=DepartureDayFormSet, extra=0)
        data = {'program_days-TOTAL_FORMS': 5, 'program_days-INITIAL_FORMS': 5,
                'program_days-MIN_NUM_FORMS': 0, 'program_days-MAX_NUM_FORMS': 1000}
        for index, day in enumerate(self.departure.program_days.all()):
            data.update({f'program_days-{index}-id': day.pk,
                         f'program_days-{index}-departure': self.departure.pk,
                         f'program_days-{index}-day_number': day.day_number})
        forms = FormSet(data, instance=self.departure, prefix='program_days')
        self.assertFalse(forms.is_valid())
        self.assertIn('at least one day', str(forms.non_form_errors()))
        self.book()
        data['program_days-0-is_visible'] = True
        forms = FormSet(data, instance=self.departure, prefix='program_days')
        self.assertFalse(forms.is_valid())
        self.assertIn('already reserved', str(forms.non_form_errors()))

    def test_new_tour_inline_respects_configured_maximum(self):
        FormSet = inlineformset_factory(Tour, TourDeparture, formset=TourDepartureFormSet,
            fields=('start_date', 'end_date', 'is_published'), extra=0)
        new_tour = Tour(title='New', destination=self.tour.destination, price_per_night=100, max_days=5)
        forms = FormSet({'departures-TOTAL_FORMS': 1, 'departures-INITIAL_FORMS': 0,
            'departures-MIN_NUM_FORMS': 0, 'departures-MAX_NUM_FORMS': 1000,
            'departures-0-start_date': self.day.isoformat(),
            'departures-0-end_date': (self.day + timedelta(days=5)).isoformat()},
            instance=new_tour, prefix='departures')
        self.assertFalse(forms.is_valid())

    def test_new_programme_day_can_select_activities_from_its_tour(self):
        activity = TourActivity.objects.create(tour=self.tour, title='New programme activity')
        FormSet = inlineformset_factory(TourDeparture, DepartureDay, form=DepartureDayForm,
            formset=DepartureDayFormSet, extra=1)
        forms = FormSet(instance=self.departure)
        self.assertIn(activity, forms.empty_form.fields['activities'].queryset)

    def test_chat_suggestions_use_only_published_available_departures(self):
        from apps.core.views import _suggest_available_ranges, _suggest_available_ranges_near
        expected = [(self.departure.start_date, self.departure.end_date)]
        self.assertEqual(_suggest_available_ranges('morocco'), expected)
        self.assertEqual(_suggest_available_ranges_near('morocco', self.day, nights=19), expected)
        self.book()
        self.assertEqual(_suggest_available_ranges('morocco'), [])

    def test_chat_cannot_bypass_departures_and_supports_one_day(self):
        self.client.force_login(self.user)
        payload = {'tour_id': self.tour.pk, 'start_date': self.day.isoformat(),
            'end_date': self.day.isoformat(), 'persons': 1, 'payment_method': 'cash'}
        self.assertEqual(self.client.post('/morocco/api/chat-book-tour/', payload,
            content_type='application/json').status_code, 409)
        single = TourDeparture.objects.create(tour=self.tour, start_date=self.day, end_date=self.day, is_published=True)
        payload['departure_id'] = single.pk
        self.assertEqual(self.client.post('/morocco/api/chat-book-tour/', payload,
            content_type='application/json').status_code, 200)
        self.assertEqual(Reservation.objects.get().total_price, 100)
