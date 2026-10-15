from django.contrib.admin import AdminSite
from django.contrib.admin.apps import AdminConfig
from django.urls import reverse


class CountryAdminSite(AdminSite):
    country = 'morocco'

    def __init__(self, name='admin', country='morocco'):
        self.country = country
        super().__init__(name)
        self.site_header = f'{country.title()} administration'
        self.site_title = self.site_header
        self.index_title = f'Manage {country.title()}'
        self.site_url = f'/{country}/'

    def each_context(self, request):
        return {**super().each_context(request), 'admin_country': self.country,
                'morocco_admin_url': reverse('admin:index', current_app='admin'),
                'ireland_admin_url': reverse('ireland_admin:index')}


class CountryAdminConfig(AdminConfig):
    default_site = 'apps.core.admin_site.CountryAdminSite'


ireland_admin = CountryAdminSite(name='ireland_admin', country='ireland')
