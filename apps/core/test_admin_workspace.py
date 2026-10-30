from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from .models import Country, Destination, Tour, Guide, Reservation


@override_settings(SECURE_SSL_REDIRECT=False)
class AdminWorkspaceTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_superuser('workspace-manager', 'manager@example.com', 'Layout-test-123!')
        self.user = User.objects.create_user('workspace-traveler', email='traveler@example.com')
        self.morocco = Country.objects.get(slug='morocco')
        self.ireland = Country.objects.get(slug='ireland')
        self.ireland.is_visible = False
        self.ireland.save()
        self.rabat = Tour.objects.create(title='Morocco workspace tour', price_per_night=100,
            destination=Destination.objects.create(name='Rabat workspace'))
        self.dublin = Tour.objects.create(title='Ireland workspace tour', country='ireland', price_per_night=100,
            destination=Destination.objects.create(name='Dublin workspace', country='ireland'))
        self.irish_guide = Guide.objects.create(country=self.ireland, name='Irish team', description='Local team')
        self.moroccan_guide = Guide.objects.create(country=self.morocco, name='Moroccan team', description='Local team')

    def choose(self, slug):
        self.client.force_login(self.staff)
        return self.client.post('/admin/workspace/select/', {'country': slug})

    def test_country_portal_and_persistent_country_lists(self):
        self.client.force_login(self.staff)
        self.assertContains(self.client.get('/admin/'), 'Choose a country to manage')
        self.assertRedirects(self.client.get('/admin/core/tour/'), '/admin/')
        self.assertRedirects(self.client.get('/admin/core/tour/add/'), '/admin/')
        self.choose('morocco')
        self.assertContains(self.client.get('/admin/'), 'Morocco workspace')
        response = self.client.get('/admin/core/tour/')
        self.assertContains(response, self.rabat.title)
        self.assertNotContains(response, self.dublin.title)
        response = self.client.get('/admin/core/guide/')
        self.assertContains(response, self.moroccan_guide.name)
        self.assertNotContains(response, self.irish_guide.name)
        self.choose('ireland')
        self.assertContains(self.client.get('/admin/core/tour/'), self.dublin.title)
        self.assertNotContains(self.client.get('/admin/core/tour/'), self.rabat.title)

    def test_new_country_forms_and_tour_selectors_are_scoped(self):
        self.choose('ireland')
        response = self.client.get('/admin/core/tour/add/')
        form = response.context['adminform'].form
        self.assertEqual(list(form.fields['country'].choices), [('ireland', 'Ireland')])
        self.assertEqual(list(form.fields['destination'].queryset), [self.dublin.destination])
        self.assertEqual(list(form.fields['guides'].queryset), [self.irish_guide])
        response = self.client.get('/admin/core/tourdeparture/add/')
        self.assertEqual(list(response.context['adminform'].form.fields['tour'].queryset), [self.dublin])
        response = self.client.post('/admin/core/destination/add/', {'country': 'morocco', 'name': 'Wrong workspace'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Destination.objects.filter(name='Wrong workspace').exists())

    def test_booking_dashboard_stays_in_selected_country(self):
        start = timezone.localdate() + timedelta(days=80)
        for tour in (self.rabat, self.dublin):
            Reservation.objects.create(user=self.user, tour=tour, start_date=start,
                end_date=start + timedelta(days=1), total_price=100)
        self.choose('ireland')
        response = self.client.get('/dashboard/reservations/')
        self.assertEqual(response.context['admin_country'], self.ireland)
        self.assertEqual({row.tour_id for row in response.context['reservations']}, {self.dublin.pk})
        response = self.client.get('/dashboard/reservations/', {'country': 'morocco'})
        self.assertEqual({row.tour_id for row in response.context['reservations']}, {self.rabat.pk})

    def test_account_menu_has_private_links_and_staff_only_management(self):
        response = self.client.get('/')
        self.assertNotContains(response, 'class="account-menu"')
        self.client.force_login(self.user)
        response = self.client.get('/')
        self.assertContains(response, 'class="account-menu"')
        self.assertContains(response, 'My reservations')
        self.assertContains(response, 'Log out')
        self.assertNotContains(response, 'Manage bookings')
        self.assertEqual(self.client.post('/admin/workspace/select/', {'country': 'ireland'}).status_code, 302)
        self.client.force_login(self.staff)
        self.assertContains(self.client.get('/'), 'Manage bookings')
