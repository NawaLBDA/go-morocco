from __future__ import annotations

from typing import Optional, Tuple

from django.urls import get_script_prefix, set_script_prefix


class CountryPrefixMiddleware:
	"""Enable multi-site routing on a single domain via path prefixes.

	Examples:
	  - /morocco/           -> serves the usual homepage in Morocco mode
	  - /ireland/tours/     -> serves the tours list in Ireland mode

	Implementation details:
	  - Detects a leading country prefix in the URL path.
	  - Strips the prefix from request.path_info so existing URL patterns match.
	  - Sets Django's script prefix so reverse()/ {% url %} include the prefix,
		meaning templates do NOT need to be rewritten.
	  - Stores the choice in session so you can browse without the prefix too.
	"""

	COUNTRY_PREFIXES = {
		"/morocco": "morocco",
		"/ireland": "ireland",
	}

	# Avoid applying the prefix behavior to these areas.
	EXCLUDED_AFTER_PREFIX = ("/admin", "/static", "/media")

	def __init__(self, get_response):
		self.get_response = get_response

	def __call__(self, request):
		original_script_prefix = get_script_prefix()

		prefix, country = self._match_country_prefix(request.path_info or "/")
		if prefix and country:
			# If someone tries /ireland/admin/, don't rewrite admin URLs.
			remainder = (request.path_info or "/")[len(prefix) :] or "/"
			if not remainder.startswith("/"):
				remainder = "/" + remainder
			if remainder.startswith(self.EXCLUDED_AFTER_PREFIX):
				prefix = None
				country = None
			else:
				# Persist choice for subsequent navigation without a prefix.
				try:
					request.session["site_country"] = country
				except Exception:
					pass

				request.site_country = country
				request.country_prefix = prefix

				# Make Django resolve URLs as if the app was mounted under /ireland/ or /morocco/.
				# Important: script prefix must end with '/'.
				set_script_prefix(prefix + "/")

				# Strip the prefix so existing URL patterns work unchanged.
				request.path_info = remainder
				request.META["SCRIPT_NAME"] = prefix

		try:
			return self.get_response(request)
		finally:
			# Prevent leaking the prefix between requests in the same thread.
			set_script_prefix(original_script_prefix)

	@classmethod
	def _match_country_prefix(cls, path: str) -> Tuple[Optional[str], Optional[str]]:
		if not path.startswith("/"):
			path = "/" + path

		for prefix, country in cls.COUNTRY_PREFIXES.items():
			if path == prefix or path.startswith(prefix + "/"):
				return prefix, country

		return None, None

