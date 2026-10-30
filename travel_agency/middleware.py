from __future__ import annotations

from typing import Optional, Tuple

from datetime import date

from django.urls import get_script_prefix, set_script_prefix


class CountryPrefixMiddleware:
    """Legacy country paths now open the same global site with a content filter."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from apps.core.models import Country
        from django.db.utils import OperationalError, ProgrammingError
        path = request.path_info or '/'
        first = path.strip('/').split('/')[0]
        if first not in {'admin', 'static', 'media', 'ireland-admin'}:
            try:
                if Country.objects.filter(slug=first, is_active=True, is_visible=True).exists():
                    request.site_country = first
                    request.path_info = path[len(first) + 1:] or '/'
            except (OperationalError, ProgrammingError):
                pass
        return self.get_response(request)


class ReservationAutoCompleteMiddleware:
	"""Auto-mark past bookings as completed.

	Keeps UX consistent: once a booked trip has ended, the reservation becomes
	'completed' so the user can book again and doesn't see stale 'booked' UI.

	Runs at most once per day per process to keep overhead minimal.
	"""

	_last_run_day: Optional[str] = None

	def __init__(self, get_response):
		self.get_response = get_response

	def __call__(self, request):
		today = date.today().isoformat()
		if self.__class__._last_run_day != today:
			try:
				from apps.core.models import Reservation
				Reservation.objects.filter(
					status='booked',
					end_date__lt=date.today(),
				).update(status='completed')
			except Exception:
				pass
			self.__class__._last_run_day = today

		return self.get_response(request)

