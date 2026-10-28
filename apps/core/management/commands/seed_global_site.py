"""Editable starter content. Re-running never replaces staff edits."""
from datetime import date
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.core.models import Country, SiteSettings, CountryContent, Destination, Tour, TourDeparture, Promotion


class Command(BaseCommand):
    help = 'Create global settings, Morocco starter experiences and a dated Christmas offer without overwriting content.'

    @transaction.atomic
    def handle(self, *args, **options):
        SiteSettings.objects.get_or_create(pk=1)
        morocco, _ = Country.objects.get_or_create(slug='morocco', defaults={
            'name': 'Morocco', 'is_active': True, 'introduction': 'Medina mornings. Atlas horizons. Nights beneath a Saharan sky.'})
        if not morocco.introduction:
            morocco.introduction = 'Medina mornings. Atlas horizons. Nights beneath a Saharan sky.'
            morocco.save(update_fields=['introduction'])
        CountryContent.objects.get_or_create(country='morocco')
        for city, title, slug, rate, description in [
            ('Marrakech', 'Marrakech & the Atlas, slowly', 'demo-marrakech-atlas', 145, 'Wander the medina, discover craft traditions and follow mountain roads into the High Atlas. A starting itinerary to personalize with our team.'),
            ('Merzouga', 'A little closer to the stars', 'demo-sahara-stars', 175, 'Follow the changing landscapes of southern Morocco, from earthen kasbahs to the quiet dunes of the Sahara. A starting itinerary to personalize.'),
            ('Chefchaouen', 'Blue streets, open horizons', 'demo-chefchaouen', 125, 'Find a slower rhythm in the blue lanes of Chefchaouen and the landscapes of the Rif. A starting itinerary to personalize with our team.'),
        ]:
            destination, _ = Destination.objects.get_or_create(country='morocco', name=city)
            tour, created = Tour.objects.get_or_create(slug=slug, defaults={
                'country': 'morocco', 'destination': destination, 'title': title,
                'price_per_night': rate, 'max_days': 5, 'description': description,
                'included': 'Local guidance\nItinerary planning',
                'not_included': 'Flights\nTravel insurance\nServices not confirmed in your booking'})
            # These dates/prices are examples, kept unpublished until the team approves them.
            if created:
                TourDeparture.objects.create(tour=tour, start_date=date(2027, 1, 10),
                    end_date=date(2027, 1, 14), max_participants=12, is_published=False)
        Promotion.objects.get_or_create(country='morocco', name='Christmas & New Year', defaults={
            'percent': 40, 'active': True, 'apply_to_all': True, 'christmas': True,
            'starts_on': date(2026, 12, 1), 'ends_on': date(2027, 1, 5)})
        self.stdout.write(self.style.SUCCESS('Starter content ready. Example departures are drafts. Christmas offer: 40%, 1 Dec 2026–5 Jan 2027; editable in admin.'))
