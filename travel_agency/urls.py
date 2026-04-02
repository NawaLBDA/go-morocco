from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView

from apps.core.seo_views import country_sitemap

urlpatterns = [
    path('admin/', admin.site.urls),
    path('robots.txt', TemplateView.as_view(template_name='robots.txt', content_type='text/plain'), name='robots_txt'),
    path('sitemap.xml', country_sitemap, name='sitemap'),
    path('', include('apps.core.urls')),
    path('', include('apps.reservations.urls')),   # ✅ include all reservation routes
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
