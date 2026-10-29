import json
from html.parser import HTMLParser
from xml.etree import ElementTree

from django.test import TestCase, override_settings

from .models import BlogPost, Destination, Tour


class HeadParser(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.meta, self.canonical, self.titles, self.schemas = {}, [], [], []
        self.in_title = self.in_schema = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta':
            self.meta[attrs.get('name', attrs.get('property'))] = attrs.get('content')
        if tag == 'link' and attrs.get('rel') == 'canonical':
            self.canonical.append(attrs['href'])
        if tag == 'title':
            self.in_title = True
            self.titles.append('')
        if tag == 'script' and attrs.get('type') == 'application/ld+json':
            self.in_schema = True
            self.schemas.append('')

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
        if tag == 'script':
            self.in_schema = False

    def handle_data(self, data):
        if self.in_title:
            self.titles[-1] += data
        if self.in_schema:
            self.schemas[-1] += data


@override_settings(
    SECURE_SSL_REDIRECT=False,
    ALLOWED_HOSTS=['testserver', 'basmamoroccoexperience.com', 'www.basmamoroccoexperience.com'],
    MOROCCO_SITE_URL='https://basmamoroccoexperience.com',
)
class MoroccoSEOTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from .models import Country
        Country.objects.filter(slug="ireland").update(is_active=False)
        destination = Destination.objects.create(name='Rabat')
        cls.tour = Tour.objects.create(title='Rabat discovery', destination=destination,
            price_per_night=100, description='A private tour of Rabat with your local guide.')
        cls.irish_tour = Tour.objects.create(title='Dublin discovery', country='ireland',
            destination=destination, price_per_night=100)
        cls.demo = Tour.objects.create(title='Demo trip', slug='demo-trip',
            destination=destination, price_per_night=50)
        cls.post = BlogPost.objects.create(title='A day in Rabat', slug='rabat-story', content='Discover Rabat and its local stories.')

    def get_head(self, path, **kwargs):
        response = self.client.get(path, HTTP_HOST='basmamoroccoexperience.com', **kwargs)
        self.assertEqual(response.status_code, 200)
        return HeadParser(response.content.decode())

    def test_unique_page_titles_and_social_metadata(self):
        titles = []
        for path in ['/', '/reservations/', '/blog/', '/contact/', '/about/']:
            with self.subTest(path=path):
                head = self.get_head(path)
                self.assertEqual(len(head.titles), 1)
                self.assertEqual(head.meta['og:title'], head.titles[0])
                self.assertEqual(head.meta['twitter:description'], head.meta['description'])
                self.assertEqual(head.canonical, ['https://basmamoroccoexperience.com' + path])
                self.assertTrue(head.meta['robots'].startswith('index'))
                titles += head.titles
        self.assertEqual(len(set(titles)), len(titles))

    def test_prefix_tracking_and_www_have_same_canonical(self):
        response = self.client.get('/morocco/contact/?utm_source=test', HTTP_HOST='www.basmamoroccoexperience.com')
        head = HeadParser(response.content.decode())
        self.assertEqual(head.canonical, ['https://basmamoroccoexperience.com/contact/'])
        self.assertTrue(head.meta['robots'].startswith('index'))

    def test_tour_metadata_and_independent_guide_schema(self):
        head = self.get_head('/tour/' + self.tour.slug + '/')
        self.assertIn(self.tour.title, head.titles[0])
        self.assertEqual(head.meta['description'], self.tour.description)
        graph = json.loads(head.schemas[0])['@graph']
        types = {node['@type'] for node in graph}
        self.assertIn('TravelAgency', types)
        self.assertIn('TouristTrip', types)
        self.assertIn('BreadcrumbList', types)
        self.assertNotIn('Person', types)

    def test_article_schema_uses_real_publication_date(self):
        head = self.get_head('/blog/' + self.post.slug + '/')
        self.assertEqual(head.meta['og:type'], 'article')
        article = next(node for node in json.loads(head.schemas[0])['@graph'] if node['@type'] == 'BlogPosting')
        self.assertEqual(article['datePublished'], self.post.created_at.isoformat())
        self.assertNotIn('dateModified', article)
        self.assertNotIn('author', article)

    def test_jsonld_cannot_close_its_script_element(self):
        self.post.title = '</script><script>alert("x")</script>'
        self.post.save()
        head = self.get_head('/blog/' + self.post.slug + '/')
        self.assertEqual(len(head.schemas), 1)
        self.assertNotIn('</script>', head.schemas[0])
        graph = json.loads(head.schemas[0])['@graph']
        self.assertEqual(next(node for node in graph if node['@type'] == 'BlogPosting')['headline'], self.post.title)

    def test_private_search_and_demo_pages_not_indexed(self):
        for path in ['/login/', '/register/', '/reservations/?q=Rabat', '/tour/demo-trip/']:
            self.assertIn('noindex', self.get_head(path).meta['robots'])
        response = self.client.get('/morocco/')
        self.assertIn('noindex', HeadParser(response.content.decode()).meta['robots'])

    def test_sitemap_uses_canonical_slug_urls_and_only_morocco(self):
        for path in ['/sitemap.xml', '/morocco/sitemap.xml']:
            response = self.client.get(path, HTTP_HOST='basmamoroccoexperience.com')
            self.assertEqual(response.status_code, 200)
            locations = [el.text for el in ElementTree.fromstring(response.content).iter() if el.tag.endswith('}loc')]
            self.assertIn('https://basmamoroccoexperience.com/tour/' + self.tour.slug + '/', locations)
            self.assertFalse(any('/morocco/' in url or 'demo-trip' in url or self.irish_tour.slug in url for url in locations))
            self.assertTrue(all(url.startswith('https://basmamoroccoexperience.com/') for url in locations))

    def test_robots_points_to_canonical_sitemap_and_preview_is_blocked(self):
        response = self.client.get('/robots.txt', HTTP_HOST='basmamoroccoexperience.com')
        self.assertTrue(response['Content-Type'].startswith('text/plain'))
        self.assertContains(response, 'Sitemap: https://basmamoroccoexperience.com/sitemap.xml')
        self.assertContains(self.client.get('/robots.txt'), 'Disallow: /')

    def test_old_numeric_tour_url_redirects_permanently(self):
        response = self.client.get(f'/morocco/tour/{self.tour.pk}/')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, '/tour/' + self.tour.slug + '/')

    def test_global_identity_does_not_change_with_host_or_old_session(self):
        session = self.client.session
        session['site_country'] = 'ireland'
        session.save()
        head = self.get_head('/')
        self.assertEqual(head.titles[0], 'Culture Hop Tours')
        response = self.client.get('/', HTTP_HOST='basmamoroccoexperience.com')
        self.assertContains(response, 'global-site')
        self.assertNotContains(response, 'morocco-layout.css')
        self.assertEqual(self.client.get('/ireland/').status_code, 404)

    def test_inactive_country_does_not_create_another_site_or_sitemap(self):
        self.assertEqual(self.client.get('/ireland/sitemap.xml').status_code, 404)
        response = self.client.get('/sitemap.xml')
        self.assertContains(response, self.tour.slug)
        self.assertNotContains(response, self.irish_tour.slug)
