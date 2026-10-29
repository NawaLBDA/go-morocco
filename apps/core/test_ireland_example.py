from django.apps import apps
from django.test import TestCase, override_settings
from .models import Tour
from .ireland_example import seed_ireland_example


@override_settings(SECURE_SSL_REDIRECT=False)
class IrelandExampleTests(TestCase):
    def setUp(self):
        seed_ireland_example(apps)

    def test_one_editable_tour_with_three_days_and_six_map_stops(self):
        tour = Tour.objects.get(slug='demo-dublin-howth-culture')
        self.assertEqual(tour.departures.count(), 1)
        self.assertEqual(tour.departures.get().active_days, 3)
        self.assertEqual(tour.activity_cards.count(), 6)
        tour.title = 'Staff reviewed Dublin'
        tour.save()
        seed_ireland_example(apps)
        tour.refresh_from_db()
        self.assertEqual(tour.title, 'Staff reviewed Dublin')
        self.assertEqual(tour.departures.count(), 1)
        response = self.client.get('/', {'country': 'ireland'})
        self.assertContains(response, 'Staff reviewed Dublin')
        self.assertContains(response, 'ireland-howth-starter.webp')
        self.assertContains(self.client.get('/'), 'ireland-coast-starter.webp')

    def test_home_and_approach_start_with_doctype_and_keep_favicon_in_head(self):
        for path in ('/', '/about/'):
            response = self.client.get(path)
            html = response.content.decode('utf-8')
            self.assertTrue(html.lstrip().startswith('<!doctype html>'), path)
            self.assertNotIn('\ufeff', html[:html.index('<html')])
            self.assertIn('/static/favicon.ico?v=3', html.split('</head>')[0])
