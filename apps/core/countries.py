"""Country validation shared by legacy slug fields and the country catalogue."""
from django.core.exceptions import ValidationError


def validate_country(value):
    from .models import Country
    if value and not Country.objects.filter(slug=value).exists():
        raise ValidationError('Choose a country from the country catalogue.')


def uses_scheduled_departures(country):
    from .models import Country
    return Country.objects.filter(slug=country, uses_scheduled_departures=True).exists()
