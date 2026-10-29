"""Booking eligibility shared by requests and waiting lists."""
from apps.core.models import UserProfile

DEAF_ONLY_MESSAGE = 'This departure is reserved for travelers registered as deaf.'


def can_book_departure(user, tour, departure=None):
    restricted = tour.deaf_only or bool(departure and departure.deaf_only)
    return not restricted or bool(user.is_authenticated and
        UserProfile.objects.filter(user=user, is_deaf=True).exists())
