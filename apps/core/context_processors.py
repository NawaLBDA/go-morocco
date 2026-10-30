import os
from .models import Country, SiteSettings, Section, Tour, BlogPost, Reservation


def get_country_from_site(request):
    """Country is content context, never a hostname or a user's nationality."""
    explicit = getattr(request, 'site_country', None) or request.GET.get('country')
    if explicit and Country.objects.filter(slug=explicit, is_active=True, is_visible=True).exists():
        return explicit
    match = getattr(request, 'resolver_match', None)
    if match:
        args = match.kwargs
        qs = Tour.objects.filter(region__is_active=True, region__is_visible=True)
        tour = None
        if args.get('tour_slug'):
            tour = qs.filter(slug=args['tour_slug']).first()
        elif args.get('tour_id'):
            tour = qs.filter(pk=args['tour_id']).first()
        if tour:
            return tour.country
        if args.get('slug') and match.url_name == 'blog_detail':
            post = BlogPost.objects.filter(slug=args['slug'], region__is_active=True, region__is_visible=True).first()
            if post:
                return post.country
        reservation_id = args.get('reservation_id') or args.get('id')
        if reservation_id:
            booking = Reservation.objects.select_related('tour').filter(pk=reservation_id).first()
            if booking:
                return booking.tour.country
    return 'morocco'


def sections_processor(request):
    from .catalogue import active_promotions
    from .admin_workspace import workspace_context
    site = SiteSettings.objects.filter(pk=1).first() or SiteSettings()
    country = get_country_from_site(request)
    promotion = active_promotions().filter(apply_to_all=True).order_by('-percent').first()
    return {
        **workspace_context(request),
        'site_settings': site, 'brand_name': site.brand_name,
        'footer_destinations': ' \u2022 '.join(Country.objects.filter(is_active=True, is_visible=True).values_list('name', flat=True)),
        'footer_brand_name': site.brand_name, 'about_brand_name': site.brand_name,
        'support_email': site.support_email,
        'country': country,
        'countries': Country.objects.filter(is_active=True, is_visible=True),
        'sections': Section.objects.filter(country=country, show_in_nav=True).order_by('order'),
        'active_promotion': promotion, 'has_promotion': bool(promotion),
        'festive_theme': site.christmas_theme and active_promotions().filter(christmas=True).exists(),
        'meta_description': 'Thoughtfully planned journeys, local connections and extraordinary memories. Starting in Morocco, looking to the world.',
        'canonical_url': request.build_absolute_uri().split('?', 1)[0],
        'scheduled_tours': Country.objects.filter(slug=country, uses_scheduled_departures=True).exists(),
        'site_lang': 'en', 'static_version': os.environ.get('STATIC_VERSION', 'global-1'),
    }
