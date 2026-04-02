from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .models import BlogPost, Tour


class StaticViewSitemap(Sitemap):
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
        ]

    def location(self, item):
        return reverse(item)


class TourSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def __init__(self, country: str = "morocco"):
        self.country = country

    def items(self):
        return Tour.objects.filter(country=self.country).order_by("id")

    def location(self, obj: Tour):
        return reverse("tour_detail", kwargs={"tour_id": obj.id})


class BlogSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.6

    def __init__(self, country: str = "morocco"):
        self.country = country

    def items(self):
        return BlogPost.objects.filter(country=self.country).order_by("-created_at")

    def location(self, obj: BlogPost):
        return reverse("blog_detail", kwargs={"slug": obj.slug})
