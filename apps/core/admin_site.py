from django.contrib.admin import AdminSite
from django.contrib.admin.apps import AdminConfig

class CountryAdminSite(AdminSite):
    country = None
    site_header = 'Culture Hop Tours | Global administration'
    site_title = 'Culture Hop Tours administration'
    index_title = 'Manage countries, journeys and bookings'
    site_url = '/'

class CountryAdminConfig(AdminConfig):
    default_site = 'apps.core.admin_site.CountryAdminSite'
