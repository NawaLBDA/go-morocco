from decimal import Decimal
from django.db.models import Q
from django.utils import timezone
from .models import Promotion, Tour


def visible_tours(user):
    return Tour.objects.filter(region__is_active=True, region__is_visible=True, region__coming_soon=False)


def active_promotions(country=None):
    today = timezone.localdate()
    qs = Promotion.objects.filter(active=True, region__is_active=True, region__is_visible=True).filter(
        Q(starts_on__isnull=True) | Q(starts_on__lte=today),
        Q(ends_on__isnull=True) | Q(ends_on__gte=today))
    return qs.filter(country=country) if country else qs


def tour_discount(tour, seasonal_percent=None):
    if tour.package_price is not None:
        return 0  # Fixed package totals keep the published minimum; legacy offers remain available.
    if seasonal_percent is None:
        seasonal = active_promotions(tour.country).filter(apply_to_all=True).order_by('-percent').first()
        seasonal_percent = seasonal.percent if seasonal else 0
    return max(0, min(100, max(tour.discount_percent if tour.is_promotion else 0, seasonal_percent)))


def tour_rate(tour, seasonal_percent=None):
    return (Decimal(tour.display_price) * (100 - tour_discount(tour, seasonal_percent)) / 100).quantize(Decimal('0.01'))
