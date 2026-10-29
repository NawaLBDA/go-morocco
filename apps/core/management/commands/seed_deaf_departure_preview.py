"""Add one labeled Rabat departure without changing existing departures or bookings."""
from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from apps.core.models import Tour, TourDeparture


class Command(BaseCommand):
    help = 'Add a published deaf-traveler example departure for Rabat; everyone can book.'

    @transaction.atomic
    def handle(self, *args, **options):
        tour = Tour.objects.filter(country='morocco', destination__name__iexact='Rabat').order_by('pk').first()
        if not tour:
            raise CommandError('Prepare Rabat first with seed_rabat_preview.')
        departure = tour.departures.filter(deaf_only=True, is_published=True, start_date__gte=timezone.localdate()).order_by('start_date').first()
        if not departure:
            start = timezone.localdate() + timedelta(days=45)
            duration = min(3, tour.max_days)
            from apps.reservations.availability import has_conflict
            while has_conflict(start, start+timedelta(days=duration-1), country=tour.country):
                start += timedelta(days=3)
            departure, _ = TourDeparture.objects.get_or_create(tour=tour, start_date=start,
                end_date=start+timedelta(days=duration-1), defaults={'deaf_only': True, 'is_published': True,
                    'max_participants': 8, 'max_concurrent_bookings': 1})
        self.stdout.write(self.style.SUCCESS(f'Rabat example: {departure.start_date} to {departure.end_date}. Reserved for travelers registered as deaf. Dates and arrangements are examples for staff to review.'))
        self.stdout.write(f'/tour/{tour.slug}/?departure_id={departure.pk}')
