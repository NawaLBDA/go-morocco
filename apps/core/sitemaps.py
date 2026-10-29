from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from types import SimpleNamespace
from urllib.parse import urlsplit

from .models import BlogPost, Tour
from .seo import morocco_url


class CountrySitemap(Sitemap):
    def get_urls(self, page=1, site=None, protocol=None):
        if self.country == 'morocco':
            origin = urlsplit(morocco_url('/'))
            site = SimpleNamespace(domain=origin.netloc)
            protocol = origin.scheme
        return super().get_urls(page=page, site=site, protocol=protocol)

    def canonical_location(self, path):
        return urlsplit(morocco_url(path)).path if self.country == 'morocco' else path


class StaticViewSitemap(CountrySitemap):
    changefreq = "weekly"
    priority = 0.8

    def __init__(self, country: str = "morocco"):
        self.country = country

    def items(self):
        # Keep this list minimal and stable.
        return [
            "home",
            "reservations",
            "blog_list",
            "contact",
            "about",
        ]

    def location(self, item):
        return self.canonical_location(reverse(item))


class TourSitemap(CountrySitemap):
    changefreq = "weekly"
    priority = 0.7

    def __init__(self, country: str = "morocco"):
        self.country = country

    def items(self):
        tours = Tour.objects.filter(region__is_active=True, region__coming_soon=False, deaf_only=False).exclude(slug__isnull=True).exclude(slug='')
        if self.country == 'morocco':
            tours = tours.exclude(slug__startswith='demo-')
        return tours.order_by("id")

    def location(self, obj: Tour):
        return self.canonical_location(reverse("tour_detail", kwargs={"tour_slug": obj.slug}))


class BlogSitemap(CountrySitemap):
    changefreq = "weekly"
    priority = 0.6

    def __init__(self, country: str = "morocco"):
        self.country = country

    def items(self):
        posts = BlogPost.objects.filter(region__is_active=True, is_demo=False)
        if self.country == 'morocco':
            posts = posts.exclude(slug__startswith='demo-')
        return posts.order_by("-created_at")

    def location(self, obj: BlogPost):
        return self.canonical_location(reverse("blog_detail", kwargs={"slug": obj.slug}))

    def lastmod(self, obj):
        return obj.created_at
