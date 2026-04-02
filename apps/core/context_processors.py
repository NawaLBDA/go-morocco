from .models import Section, Tour
from django.db.utils import OperationalError, ProgrammingError

def get_country_from_site(request):
    # Prefer host-based detection so maroc.local / ireland.local always win.
    host = request.get_host().split(':')[0].lower()

    # Morocco must win for maroc.local (even if host contains other words)
    if host in {'maroc.local', 'maroc.lcoal', 'morocco.local'} or 'maroc' in host or 'morocco' in host:
        return 'morocco'

    if 'ireland' in host:
        return 'ireland'

    # Fallback: user profile (only when host does not indicate a country)
    if request.user.is_authenticated:
        try:
            profile = request.user.profile
            profile_country = (profile.country or '').lower().strip()
            if profile_country in ['morocco', 'ireland']:
                return profile_country
        except Exception:
            pass

    return 'morocco'

def sections_processor(request):
    country = get_country_from_site(request)

    # Brand/contact configuration per country
    brand_name = 'Basma'
    support_email = 'info@basma.ma'
    whatsapp_number = '+212 643 092 852'
    whatsapp_wa_digits = '212643092852'

    if country == 'ireland':
        brand_name = 'Bayo'
        support_email = 'info@bayo.ie'
        # Display number requested by user; wa.me requires country code
        whatsapp_number = '0644061453'
        whatsapp_wa_digits = '353644061453'

    whatsapp_link = f"https://wa.me/{whatsapp_wa_digits}"

    try:
        sections = Section.objects.filter(show_in_nav=True, country=country).order_by('order')
        # ✅ Check if there are any promotions to display the promo bar
        has_promotion = Tour.objects.filter(is_promotion=True, discount_percent__gt=0, country=country).exists()
    except (OperationalError, ProgrammingError):
        sections = []
        has_promotion = False

    return {
        'sections': sections,
        'has_promotion': has_promotion,
        'country': country,
        'brand_name': brand_name,
        'support_email': support_email,
        'whatsapp_number': whatsapp_number,
        'whatsapp_link': whatsapp_link,
    }
