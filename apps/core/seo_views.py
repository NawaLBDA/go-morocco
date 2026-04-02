from django.contrib.sitemaps.views import sitemap as sitemap_view

from .context_processors import get_country_from_site
from .sitemaps import BlogSitemap, StaticViewSitemap, TourSitemap


def country_sitemap(request):
    """Sitemap that respects the current country (morocco/ireland).

    This works with the Render single-domain setup because the prefix middleware
    sets the script prefix, so URLs in the sitemap include /morocco/ or /ireland/.
    """

    country = get_country_from_site(request)

    sitemaps = {
        "static": StaticViewSitemap(country=country),
        "tours": TourSitemap(country=country),
        "blog": BlogSitemap(country=country),
    }

    return sitemap_view(request, sitemaps)
