from datetime import date, timedelta
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch
from importlib import import_module
from django.apps import apps
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, override_settings
from django.utils import timezone
from .catalogue_examples import seed_examples
from .models import Country, Destination, Tour, TourDeparture, TourActivity, Reservation


@override_settings(SECURE_SSL_REDIRECT=False)
class CountryExampleTests(TestCase):
    def test_requested_catalogue_contains_two_countries_five_trips_and_open_deaf_departures(self):
        result=seed_examples(apps, activate_countries=True)
        self.assertEqual(result, {'tours_created':5,'departures_created':10})
        self.assertEqual(Tour.objects.filter(slug__endswith='-culture').count(),5)
        self.assertTrue(Country.objects.get(slug='nigeria').is_active)
        self.assertEqual(TourDeparture.objects.filter(deaf_only=True).count(),5)
        for tour in Tour.objects.filter(slug__endswith='-culture'):
            self.assertEqual(tour.activity_cards.count(),6)
            self.assertEqual(tour.itinerary_legs.count(),3)
            self.assertEqual(tour.departures.count(),2)
            for departure in tour.departures.all():
                self.assertEqual(departure.active_days,3)
                self.assertTrue(all(day.activities.count()==2 for day in departure.program_days.all()))
        response=self.client.get('/reservations/',{'country':'nigeria'})
        self.assertContains(response,'Lagos: art, city life')
        self.assertContains(response,'Abuja: crafts')
        self.assertContains(response,'Everyone welcome',count=4)  # accessible name + visible text on two badges
        self.assertNotContains(response,'Tangier: sea views')
        self.assertContains(response,'nigeria-hero.webp')
        user=User.objects.create_user('hearing-traveler',email='test@example.com')
        self.client.force_login(user)
        departure=TourDeparture.objects.filter(tour__country='nigeria',deaf_only=True).first()
        response=self.client.get(f'/tour/{departure.tour.slug}/',{'departure_id':departure.pk})
        self.assertContains(response,'id="booking-form"')

    def test_repeated_seed_preserves_staff_edits_and_does_not_recreate_deleted_dates(self):
        seed_examples(apps,activate_countries=True)
        tour=Tour.objects.get(slug='demo-rabat-culture')
        tour.title='Staff revised this journey';tour.price_per_night=321;tour.save()
        stop=tour.activity_cards.first();stop.title='Staff stop';stop.save()
        tour.departures.first().delete()
        Country.objects.filter(slug='nigeria').update(is_active=False,introduction='Team introduction')
        result=seed_examples(apps,today=timezone.localdate()+timedelta(days=90))
        self.assertEqual(result,{'tours_created':0,'departures_created':0})
        tour.refresh_from_db();stop.refresh_from_db()
        self.assertEqual(tour.title,'Staff revised this journey')
        self.assertEqual(tour.price_per_night,321)
        self.assertEqual(stop.title,'Staff stop')
        self.assertEqual(tour.departures.count(),1)
        self.assertFalse(Country.objects.get(slug='nigeria').is_active)

    def test_existing_paid_booking_and_original_tour_are_preserved(self):
        day=timezone.localdate()+timedelta(days=30)
        original=Tour.objects.create(title='Original staff Rabat',price_per_night=750,
            destination=Destination.objects.create(name='Rabat'),image='existing/rabat-image')
        user=User.objects.create_user('existing-customer')
        reservation=Reservation.objects.create(user=user,tour=original,start_date=day,end_date=day+timedelta(days=2),
            num_persons=2,total_price=4500,status='booked',payment_status='paid')
        before=Reservation.objects.values().get(pk=reservation.pk)
        call_command('seed_country_examples','--activate-countries',stdout=StringIO())
        original.refresh_from_db()
        self.assertEqual(original.title,'Original staff Rabat')
        self.assertEqual(original.price_per_night,750)
        self.assertEqual(Reservation.objects.values().get(pk=reservation.pk),before)
        self.assertEqual(Reservation.objects.count(),1)
        sample=Tour.objects.get(slug='demo-rabat-culture')
        self.assertEqual(str(sample.image),str(original.image))
        self.assertGreater(sample.departures.order_by('start_date').first().start_date,reservation.end_date)

    def test_render_migration_uses_historical_models_and_creates_complete_programmes(self):
        registry=MigrationExecutor(connection).loader.project_state([('core','0052_separate_travel_memories')]).apps
        module=import_module('apps.core.migrations.0050_render_country_examples')
        with patch.dict('os.environ',{'RENDER':'true'}):
            module.populate_requested_render_catalogue(registry,SimpleNamespace(connection=connection))
        self.assertEqual(TourDeparture.objects.count(),10)
        self.assertEqual(TourActivity.objects.count(),30)
        self.assertEqual(TourDeparture.objects.first().active_days,3)
