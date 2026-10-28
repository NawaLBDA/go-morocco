from django.contrib.sitemaps.views import sitemap as sitemap_view
from django.shortcuts import render

from .context_processors import get_country_from_site
from .sitemaps import BlogSitemap, StaticViewSitemap, TourSitemap
from .seo import is_local_preview, morocco_url


def country_sitemap(request):
    """One sitemap for every active country on the global site."""

    country = get_country_from_site(request)

    sitemaps = {
        "static": StaticViewSitemap(country=country),
        "tours": TourSitemap(country=country),
        "blog": BlogSitemap(country=country),
    }

    return sitemap_view(request, sitemaps)


def robots_txt(request):
    country = get_country_from_site(request)
    return render(request, 'robots.txt', {
        'morocco_robots': True,
        'local_preview': is_local_preview(request),
        'sitemap_url': morocco_url('/sitemap.xml'),
    }, content_type='text/plain')
