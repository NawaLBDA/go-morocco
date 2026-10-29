from datetime import date, timedelta
from importlib import import_module
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch
from django.apps import apps
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, override_settings
from django.utils import timezone
from .models import BlogPost, Country, Tour, Destination, TourDeparture
from .memory_examples import seed_memory_examples
from .sitemaps import BlogSitemap


@override_settings(SECURE_SSL_REDIRECT=False)
class MemoryJournalTests(TestCase):
    def setUp(self):
        Country.objects.get_or_create(slug='nigeria',defaults={'name':'Nigeria','is_active':True})
        Country.objects.filter(slug='nigeria').update(is_active=True)

    def test_journal_has_no_booking_catalogue_or_planning_articles(self):
        memory=BlogPost.objects.create(title='A genuine old memory',slug='real-memory',country='morocco',content='A shared moment.',trip_date=date(2024,6,3))
        BlogPost.objects.create(title='A future itinerary to plan',slug='planning-only',country='morocco',content='Choose a future trip.',story_kind='inspiration')
        tour=Tour.objects.create(title='Future trip should stay elsewhere',destination=Destination.objects.create(name='Rabat'),price_per_night=100)
        start=timezone.localdate()+timedelta(days=400)
        TourDeparture.objects.create(tour=tour,start_date=start,end_date=start+timedelta(days=2),is_published=True)
        with patch('apps.core.global_views.catalogue_data',side_effect=AssertionError('The memory page must not query the booking catalogue')):
            response=self.client.get('/blog/')
        self.assertContains(response,memory.title)
        self.assertNotContains(response,'A future itinerary to plan')
        self.assertNotContains(response,tour.title)
        self.assertNotContains(response,'dated-grid')
        self.assertNotContains(response,'country-tours')
        self.assertNotIn(start.year,response.context['years'])
        self.assertContains(self.client.get('/blog/',{'year':'2024'}),memory.title)
        self.assertEqual(self.client.get('/blog/',{'year':'bad'}).status_code,404)
        self.assertEqual(self.client.get('/blog/',{'country':'unknown'}).status_code,404)

    def test_demo_memories_are_disclosed_filterable_and_idempotent(self):
        self.assertEqual(seed_memory_examples(apps),3)
        response=self.client.get('/blog/')
        self.assertContains(response,'class="memory-demo-badge"',count=3)
        self.assertContains(response,'Fictional story',count=3)
        self.assertContains(response,'demo-memory-rabat.webp')
        self.assertContains(response,'country-moments')
        self.assertEqual(len(response.context['posts']),3)
        response=self.client.get('/blog/',{'country':'nigeria'})
        self.assertContains(response,'A shared moment of colour in Lagos')
        self.assertNotContains(response,'An afternoon above the river')
        self.assertEqual(len(response.context['posts']),1)
        post=BlogPost.objects.get(slug='demo-memory-rabat-river')
        post.title='Staff changed this title';post.save()
        call_command('seed_memory_examples',stdout=StringIO())
        post.refresh_from_db();self.assertEqual(post.title,'Staff changed this title')
        self.assertEqual(BlogPost.objects.count(),3)
        self.assertFalse(BlogSitemap().items().filter(pk=post.pk).exists())
        page=self.client.get('/blog/'+post.slug+'/')
        self.assertContains(page,'They do not document an actual Culture Hop Tours trip')
        self.assertContains(page,'noindex, follow')
        self.assertContains(page,'AI-generated demo illustration:')

    def test_uploaded_real_cover_takes_priority_over_starter_image(self):
        seed_memory_examples(apps)
        post=BlogPost.objects.get(slug='demo-memory-lagos-creative')
        self.assertIn('demo-memory-lagos.webp',post.cover_url)
        post.image='real-trip/uploaded-photo';post.save()
        post.refresh_from_db()
        self.assertIn('real-trip/uploaded-photo',post.cover_url)
        self.assertNotIn('demo-memory-lagos.webp',post.cover_url)

    def test_render_migration_classifies_starter_articles_without_changing_their_text(self):
        post=BlogPost.objects.create(slug='starter-morocco-city-connections',country='morocco',title='Original inspiration',content='Staff content stays.')
        registry=MigrationExecutor(connection).loader.project_state([('core','0052_separate_travel_memories')]).apps
        module=import_module('apps.core.migrations.0052_separate_travel_memories')
        with patch.dict('os.environ',{'RENDER':'true'}):
            module.classify_articles_and_add_render_examples(registry,SimpleNamespace(connection=connection))
        post.refresh_from_db()
        self.assertEqual(post.story_kind,'inspiration')
        self.assertEqual(post.content,'Staff content stays.')
        self.assertEqual(BlogPost.objects.filter(is_demo=True).count(),3)
        self.assertEqual(len(self.client.get('/blog/').context['posts']),3)
