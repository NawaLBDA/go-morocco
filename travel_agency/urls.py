from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from apps.core.seo_views import country_sitemap, robots_txt
from apps.core.admin_site import ireland_admin

for model, model_admin in admin.site._registry.items():
    if not ireland_admin.is_registered(model):
        ireland_admin.register(model, model_admin.__class__)

urlpatterns = [
    path('ireland-admin/', ireland_admin.urls),
    path('admin/', admin.site.urls),
    path('robots.txt', robots_txt, name='robots_txt'),
    path('sitemap.xml', country_sitemap, name='sitemap'),
    path('', include('apps.core.urls')),
    path('', include('apps.reservations.urls')),   # ✅ include all reservation routes
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
