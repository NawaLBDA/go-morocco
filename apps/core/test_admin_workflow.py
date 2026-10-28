from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from .models import Country, Destination, Tour, TourActivity, TourDeparture, Reservation, ContactMessage


@override_settings(SECURE_SSL_REDIRECT=False)
class AdminWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('site-manager', 'manager@example.test', 'test-password')
        self.client.force_login(self.user)
        Country.objects.filter(slug='ireland').update(is_active=True)
        self.day = date.today() + timedelta(days=60)
        self.rabat = Tour.objects.create(title='Rabat programme', price_per_night=100,
            destination=Destination.objects.create(name='Rabat', country='morocco'))
        self.dublin = Tour.objects.create(title='Dublin programme', price_per_night=80, country='ireland',
            destination=Destination.objects.create(name='Dublin', country='ireland'))
        self.first = TourActivity.objects.create(tour=self.rabat, title='Kasbah visit', day_number=1)
        self.second = TourActivity.objects.create(tour=self.rabat, title='Museum visit', day_number=2)

    def test_departure_add_has_no_manual_day_or_activity_form(self):
        response = self.client.get('/admin/core/tourdeparture/add/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id_program_days-TOTAL_FORMS')
        self.assertNotContains(response, 'id_program_days-TOTAL_FORMS')
        self.assertContains(response, 'departure-tour-data')

    def test_published_departure_without_days_form_generates_full_itinerary(self):
        response = self.client.post('/admin/core/tourdeparture/add/', {
            'tour': self.rabat.pk, 'max_participants': 12, 'start_date': self.day.isoformat(), 'end_date': '', 'is_published': 'on', '_save': 'Save'})
        self.assertEqual(response.status_code, 302)
        departure = TourDeparture.objects.get()
        self.assertEqual(departure.end_date, self.day + timedelta(days=4))
        self.assertEqual(departure.program_days.count(), 5)
        self.assertEqual(list(departure.program_days.get(day_number=1).activities.all()), [self.first])
        self.assertEqual(list(departure.program_days.get(day_number=2).activities.all()), [self.second])

    def test_old_manual_day_payload_no_longer_causes_duplicate_day_server_error(self):
        response = self.client.post('/admin/core/tourdeparture/add/', {
            'tour': self.rabat.pk, 'max_participants': 12, 'start_date': self.day.isoformat(), 'end_date': self.day.isoformat(), 'is_published': 'on',
            'program_days-TOTAL_FORMS': 1, 'program_days-INITIAL_FORMS': 0,
            'program_days-MIN_NUM_FORMS': 0, 'program_days-MAX_NUM_FORMS': 1000,
            'program_days-0-day_number': 1, 'program_days-0-is_visible': 'on',
            'program_days-0-activities': [self.first.pk], '_save': 'Save'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TourDeparture.objects.get().program_days.count(), 1)

    def test_bad_dates_return_form_errors_not_server_errors(self):
        response = self.client.post('/admin/core/tourdeparture/add/', {
            'tour': self.rabat.pk, 'start_date': 'invalid', 'end_date': '', 'is_published': 'on'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'errornote')
        self.assertFalse(TourDeparture.objects.exists())

    def test_shortening_departure_removes_generated_trailing_days_without_error(self):
        departure = TourDeparture.objects.create(tour=self.rabat, start_date=self.day,
            end_date=self.day + timedelta(days=4), is_published=True)
        data = {'max_participants': 12, 'start_date': self.day.isoformat(), 'end_date': self.day.isoformat(), 'is_published': 'on',
            'program_days-TOTAL_FORMS': 5, 'program_days-INITIAL_FORMS': 5,
            'program_days-MIN_NUM_FORMS': 0, 'program_days-MAX_NUM_FORMS': 0, '_continue': 'Save'}
        for index, day in enumerate(departure.program_days.all()):
            data.update({f'program_days-{index}-id': day.pk, f'program_days-{index}-departure': departure.pk,
                         f'program_days-{index}-is_visible': 'on'})
        response = self.client.post(f'/admin/core/tourdeparture/{departure.pk}/change/', data)
        self.assertEqual(response.status_code, 302)
        departure.refresh_from_db()
        self.assertEqual(departure.program_days.count(), 1)
        self.assertEqual(departure.end_date, self.day)

    def test_shared_destination_migration_creates_independent_country_records(self):
        from importlib import import_module
        from django.apps import apps
        from django.db import connection
        self.dublin.destination = self.rabat.destination
        self.dublin.save()
        migration = import_module('apps.core.migrations.0033_contactmessage_country_destination_country_and_more')
        with connection.schema_editor(atomic=False) as editor:
            migration.separate_existing_data(apps, editor)
        self.dublin.refresh_from_db()
        self.rabat.refresh_from_db()
        self.assertNotEqual(self.dublin.destination_id, self.rabat.destination_id)
        self.assertEqual(self.dublin.destination.country, 'ireland')
        self.assertEqual(self.rabat.destination.country, 'morocco')

    def test_programme_change_form_only_offers_inclusion_switches(self):
        departure = TourDeparture.objects.create(tour=self.rabat, start_date=self.day, end_date=self.day)
        response = self.client.get(f'/admin/core/tourdeparture/{departure.pk}/change/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Kasbah visit')
        self.assertContains(response, 'program_days-0-is_visible')
        self.assertNotContains(response, 'name="program_days-0-activities"')
        self.assertNotContains(response, 'name="program_days-0-day_number"')
        self.assertFalse(response.context['inline_admin_formsets'][0].has_add_permission)

    def test_global_admin_lists_and_edits_all_countries_with_explicit_filters(self):
        response = self.client.get('/admin/core/tour/')
        self.assertContains(response, self.rabat.title)
        self.assertContains(response, self.dublin.title)
        response = self.client.get('/admin/core/tour/', {'country': 'morocco'})
        self.assertContains(response, self.rabat.title)
        self.assertNotContains(response, self.dublin.title)
        response = self.client.get('/admin/core/tourdeparture/add/')
        field = response.context['adminform'].form.fields['tour']
        self.assertIn(self.rabat, field.queryset)
        self.assertIn(self.dublin, field.queryset)
        self.assertEqual(self.client.get(f'/admin/core/tour/{self.dublin.pk}/change/').status_code, 200)

    def test_irish_destination_creation_stays_in_irish_site(self):
        response = self.client.post('/admin/core/destination/add/', {'country': 'ireland',
            'name': 'Cork', 'description': '', 'gallery-TOTAL_FORMS': 0, 'gallery-INITIAL_FORMS': 0,
            'gallery-MIN_NUM_FORMS': 0, 'gallery-MAX_NUM_FORMS': 1000, '_save': 'Save'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Destination.objects.get(name='Cork').country, 'ireland')

    def test_dashboard_actions_exports_and_counts_stay_in_country(self):
        ours = Reservation.objects.create(user=self.user, tour=self.rabat, start_date=self.day,
            end_date=self.day + timedelta(days=1), total_price=100, payment_method='cash')
        other = Reservation.objects.create(user=self.user, tour=self.dublin, start_date=self.day,
            end_date=self.day + timedelta(days=1), total_price=80)
        response = self.client.get('/morocco/dashboard/reservations/')
        self.assertEqual(response.context['reservations_count'], 1)
        self.assertContains(response, '1 items')
        self.assertContains(response, 'fa-pen')
        self.assertContains(response, 'fa-money-bill-wave')
        self.assertNotContains(response, self.dublin.title)
        response = self.client.post('/morocco/dashboard/reservations/', {'action': 'download_report', 'reservation_ids': [other.pk]})
        self.assertNotIn(self.dublin.title.encode(), response.content)
        for action in ['validate', 'reject', 'paid', 'cancel', 'delete', 'update']:
            response = self.client.post(f'/morocco/dashboard/reservation/{other.pk}/{action}/')
            self.assertEqual(response.status_code, 404, action)
        self.assertEqual(self.client.get(f'/morocco/dashboard/reservation/{ours.pk}/validate/').status_code, 405)
        self.assertEqual(self.client.post(f'/morocco/dashboard/reservation/{ours.pk}/validate/').status_code, 302)
        ours.refresh_from_db()
        self.assertEqual(ours.status, 'booked')

    def test_contact_messages_record_their_site(self):
        for country in ['morocco', 'ireland']:
            self.client.post(f'/{country}/contact/', {'name': 'Guest', 'email': 'guest@example.test', 'message': 'Question'})
        self.assertEqual(set(ContactMessage.objects.values_list('country', flat=True)), {'morocco', 'ireland'})
