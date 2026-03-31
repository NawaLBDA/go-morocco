from .models import Section, Tour

def get_country_from_site(request):
    # First, check if user is logged in and has a country in profile
    if request.user.is_authenticated:
        try:
            profile = request.user.profile
            if profile.country.lower() in ['morocco', 'ireland']:
                return profile.country.lower()
        except:
            pass

    # Fallback to host-based detection
    host = request.get_host().split(':')[0].lower()
    if 'maroc' in host:
        return 'morocco'
    elif 'ireland' in host:
        return 'ireland'
    return 'morocco'

def sections_processor(request):
    country = get_country_from_site(request)
    sections = Section.objects.filter(show_in_nav=True, country=country).order_by('order')
    # ✅ Check if there are any promotions to display the promo bar
    has_promotion = Tour.objects.filter(is_promotion=True, discount_percent__gt=0, country=country).exists()
    return {'sections': sections, 'has_promotion': has_promotion, 'country': country}
