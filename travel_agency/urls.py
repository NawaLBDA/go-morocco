from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from apps.core.seo_views import country_sitemap, robots_txt

urlpatterns = [
    path('admin/', admin.site.urls),
    path('robots.txt', robots_txt, name='robots_txt'),
    path('sitemap.xml', country_sitemap, name='sitemap'),
    path('', include('apps.core.urls')),
    path('', include('apps.reservations.urls')),   # ✅ include all reservation routes
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
