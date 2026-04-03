import os
import json

from .models import Section, Tour
from django.db.utils import OperationalError, ProgrammingError
from django.templatetags.static import static as static_url

def get_country_from_site(request):
    # 1) Explicit override via middleware/session (Render single-domain support)
    override = getattr(request, 'site_country', None) or request.session.get('site_country')
    if override in {'morocco', 'ireland'}:
        return override

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

    # SEO defaults
    try:
        canonical_url = request.build_absolute_uri().split('?', 1)[0]
    except Exception:
        canonical_url = ''

    if country == 'ireland':
        meta_description = (
            f"Explore Ireland with {brand_name}: local taxi-driver tours, flexible pickup, and friendly guidance."
        )
        og_image_url = request.build_absolute_uri('/static/img/hero2-ir.jpg') if canonical_url else ''
        site_lang = 'en'
    else:
        meta_description = (
            f"Discover authentic Morocco experiences with {brand_name}: curated tours, trusted drivers, and seamless planning."
        )
        og_image_url = request.build_absolute_uri('/static/img/hero-ma.jpg') if canonical_url else ''
        site_lang = 'en'

    # Basic Schema.org structured data (helps Lighthouse SEO)
    schema_ld_json = ''
    try:
        base_url = request.build_absolute_uri('/')
        if country == 'ireland':
            logo = static_url('img/logo1-ir1.png')
            area_served = 'IE'
        else:
            logo = static_url('img/logo4.webp')
            area_served = 'MA'

        org_id = f"{base_url}#organization"
        site_id = f"{base_url}#website"

        graph = [
            {
                "@type": "TravelAgency",
                "@id": org_id,
                "name": brand_name,
                "url": base_url,
                "logo": request.build_absolute_uri(logo),
                "email": support_email,
                "telephone": whatsapp_number,
                "areaServed": area_served,
            },
            {
                "@type": "WebSite",
                "@id": site_id,
                "url": base_url,
                "name": brand_name,
                "publisher": {"@id": org_id},
                "inLanguage": site_lang,
            },
        ]

        if canonical_url:
            graph.append(
                {
                    "@type": "WebPage",
                    "@id": f"{canonical_url}#webpage",
                    "url": canonical_url,
                    "name": f"{brand_name} | {'Ireland' if country == 'ireland' else 'Morocco'} Tours",
                    "description": meta_description,
                    "isPartOf": {"@id": site_id},
                    "about": {"@id": org_id},
                    "inLanguage": site_lang,
                }
            )

        schema_ld_json = json.dumps({"@context": "https://schema.org", "@graph": graph})
    except Exception:
        schema_ld_json = ''

    static_version = (
        os.environ.get('STATIC_VERSION')
        or os.environ.get('RENDER_GIT_COMMIT')
        or ''
    )
    static_version = (static_version or '1')[:12]

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
        'canonical_url': canonical_url,
        'meta_description': meta_description,
        'og_image_url': og_image_url,
        'site_lang': site_lang,
        'static_version': static_version,
        'schema_ld_json': schema_ld_json,
    }
