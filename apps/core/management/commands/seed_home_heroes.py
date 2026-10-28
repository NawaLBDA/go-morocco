from django.core.management.base import BaseCommand
from django.db import transaction
from apps.core.models import Country, SiteSettings, HomeHero


class Command(BaseCommand):
    help = 'Add editable Morocco and Nigeria homepage hero slides without opening Nigeria bookings.'

    @transaction.atomic
    def handle(self, *args, **options):
        site, _ = SiteSettings.objects.get_or_create(pk=1)
        morocco, _ = Country.objects.get_or_create(slug='morocco', defaults={'name': 'Morocco', 'is_active': True})
        nigeria, _ = Country.objects.get_or_create(slug='nigeria', defaults={'name': 'Nigeria', 'is_active': False})
        HomeHero.objects.get_or_create(settings=site, country=morocco, defaults={'title': site.hero_title,
            'subtitle': site.hero_subtitle, 'caption': 'MOROCCO · WHERE OUR JOURNEY BEGINS', 'starter_image': 'morocco', 'image': site.hero_image, 'order': 0})
        HomeHero.objects.get_or_create(settings=site, country=nigeria, defaults={'title': 'New horizons. A world of possibility.',
            'subtitle': 'Discover the places that inspire our next chapter. Tell us where your curiosity will take you.',
            'caption': 'NIGERIA · DESTINATION INSPIRATION · ILLUSTRATIVE IMAGE', 'starter_image': 'nigeria', 'order': 1})
        self.stdout.write(self.style.SUCCESS('Morocco and Nigeria slides ready. Add images and more slides in Global website settings. Nigeria availability was preserved.'))
