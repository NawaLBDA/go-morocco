from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TestCase, override_settings
from .models import Country, Destination, Guide, SiteSettings, Tour


@override_settings(SECURE_SSL_REDIRECT=False)
class GuidingTeamTests(TestCase):
    def setUp(self):
        self.country = Country.objects.get(slug='morocco')
        self.other_country = Country.objects.get(slug='ireland')
        self.tour = Tour.objects.create(title='Atlas discovery', price_per_night=100,
            destination=Destination.objects.create(name='Atlas'))
        self.first = Guide.objects.create(country=self.country, name='Samira',
            photo='img/guides/samira.jpg', description='Local culture and mountain walks.', order=2)
        self.second = Guide.objects.create(country=self.country, name='Youssef',
            description='Medina stories and local traditions.', order=1)
        self.inactive = Guide.objects.create(country=self.country, name='Hidden guide',
            description='Not available.', is_active=False)
        self.foreign = Guide.objects.create(country=self.other_country, name='Irish guide',
            description='Ireland only.')

    def detail(self):
        return self.client.get('/tour/' + self.tour.slug + '/')

    def test_country_team_shows_photos_names_descriptions_in_order(self):
        response = self.detail()
        self.assertContains(response, 'Meet your local team')
        self.assertContains(response, 'Samira')
        self.assertContains(response, 'img/guides/samira.jpg')
        self.assertContains(response, 'Local culture and mountain walks.')
        self.assertContains(response, 'Youssef')
        self.assertNotContains(response, 'Hidden guide')
        self.assertNotContains(response, 'Irish guide')
        self.assertLess(response.content.index(b'Youssef'), response.content.index(b'Samira'))

    def test_specific_tour_team_overrides_country_team_and_supports_multiple_guides(self):
        self.tour.guides.add(self.first)
        self.assertContains(self.detail(), 'Samira')
        self.assertNotContains(self.detail(), 'Youssef')
        self.tour.guides.add(self.second)
        self.assertContains(self.detail(), 'Youssef')
        self.first.is_active = False
        self.first.save()
        self.assertNotContains(self.detail(), 'Samira')

    def test_foreign_guides_are_rejected_in_both_relation_directions(self):
        with self.assertRaises(ValidationError), transaction.atomic():
            self.tour.guides.add(self.foreign)
        with self.assertRaises(ValidationError), transaction.atomic():
            self.foreign.tours.add(self.tour)
        self.assertFalse(self.tour.guides.exists())

    def test_empty_team_shows_contact_message(self):
        Guide.objects.all().delete()
        self.assertContains(self.detail(), 'Your local guiding team is being arranged.')

    def test_admin_country_inline_and_tour_choices(self):
        staff = User.objects.create_superuser('team-manager', 'manager@example.com', 'test')
        self.client.force_login(staff)
        response = self.client.get(f'/admin/core/country/{self.country.pk}/change/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Samira')
        self.assertNotContains(response, 'Irish guide')
        response = self.client.get(f'/admin/core/tour/{self.tour.pk}/change/')
        self.assertEqual(response.status_code, 200)
        field = response.context['adminform'].form.fields['guides']
        self.assertIn(self.first, field.queryset)
        self.assertNotIn(self.foreign, field.queryset)
        self.client.post('/admin/workspace/select/', {'country': 'ireland'})
        self.assertContains(self.client.get('/admin/core/guide/'), 'Irish guide')

    def test_brand_slogan_and_horizons_appear_without_changing_the_domain(self):
        response = self.client.get('/')
        self.assertContains(response, 'Culture Hop Tours')
        self.assertContains(response, 'Many cultures. Unforgettable journeys.')
        self.assertContains(response, 'Nigeria • Morocco • Ireland • Jamaica')
        self.assertNotContains(response, '> Basma<')
        self.assertEqual(SiteSettings.objects.get(pk=1).brand_name, 'Culture Hop Tours')
