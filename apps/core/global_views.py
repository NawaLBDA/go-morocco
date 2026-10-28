"""Country-first travel catalogues with one card per published departure."""
from collections import OrderedDict, defaultdict
from datetime import date
from django.db.models import Q, Count
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone
from .catalogue import visible_tours, tour_rate, tour_discount, active_promotions
from .models import Country, TourDeparture, BlogPost, BlogImage, Reservation
from apps.reservations.availability import departure_capacity


def catalogue_data(request, *, stories=False):
    selected = request.GET.get('country') or getattr(request, 'site_country', '')
    countries = list(Country.objects.filter(is_active=True))
    selected_record = next((c for c in countries if c.slug == selected), None)
    if selected and not selected_record:
        raise Http404('This destination is not currently available.')
    tours = visible_tours(request.user).select_related('destination', 'region')
    query = request.GET.get('q', '').strip()[:200]
    if query:
        tours = tours.filter(Q(title__icontains=query) | Q(destination__name__icontains=query) | Q(region__name__icontains=query))
    all_departures = TourDeparture.objects.filter(tour__in=tours, is_published=True).select_related(
        'tour', 'tour__region', 'tour__destination').annotate(
        billable_count=Count('program_days', filter=Q(program_days__is_visible=True), distinct=True))
    years = set(all_departures.values_list('start_date__year', flat=True))
    if stories:
        years.update(timezone.localtime(value).year for value in BlogPost.objects.filter(region__is_active=True).values_list('created_at', flat=True) if value is not None)
    years.add(timezone.localdate().year)
    year_raw = request.GET.get('year', '')
    try:
        year = int(year_raw) if year_raw else None
        if year is not None and not 1900 <= year <= 9999:
            raise ValueError
    except ValueError:
        raise Http404('Choose a valid year.')
    if year is not None:
        years.add(year)
        all_departures = all_departures.filter(start_date__year=year)
    else:
        all_departures = all_departures.filter(start_date__gte=timezone.localdate())
    month = request.GET.get('month', '')
    if month:
        try:
            from datetime import datetime
            parsed = datetime.strptime(month, '%Y-%m')
            all_departures = all_departures.filter(start_date__year=parsed.year, start_date__month=parsed.month)
        except ValueError:
            month = ''
    for parameter, lookup in [('start_date', 'start_date__gte'), ('end_date', 'end_date__lte')]:
        if request.GET.get(parameter):
            try:
                all_departures = all_departures.filter(**{lookup: date.fromisoformat(request.GET[parameter])})
            except ValueError:
                pass
    rows = list(Reservation.objects.filter(tour__country__in=[c.slug for c in countries],
        status__in=['pending', 'booked']).values('id', 'tour__country', 'start_date', 'end_date', 'departure_id', 'num_persons'))
    rows_by_country = defaultdict(list)
    for row in rows:
        rows_by_country[row['tour__country']].append(row)
    seasonal = {}
    for promotion in active_promotions().filter(apply_to_all=True):
        seasonal[promotion.country] = max(seasonal.get(promotion.country, 0), promotion.percent)
    story_counts = {}
    if stories:
        story_query = BlogPost.objects.filter(region__is_active=True)
        if year:
            story_query = story_query.filter(created_at__year=year)
        story_counts = dict(story_query.values('country').annotate(total=Count('pk')).values_list('country', 'total'))
    country_map = {c.slug: c for c in countries}
    for country in countries:
        country.available_count = country.departure_count = country.booked_travelers = 0
        country.available_tours = set()
        country.story_count = story_counts.get(country.slug, 0)
    departures = []
    for departure in all_departures.order_by('start_date', 'pk'):
        if not departure.billable_count or departure.duration_days > departure.tour.max_days:
            continue
        country = country_map[departure.tour.country]
        capacity = departure_capacity(departure, rows=rows_by_country[country.slug], country_limit=country.max_concurrent_groups)
        departure.is_past = departure.start_date < timezone.localdate()
        for key, value in capacity.items():
            setattr(departure, key, value)
        departure.available = departure.available and not departure.is_past
        departure.rate = tour_rate(departure.tour, seasonal.get(country.slug, 0))
        departure.discount = tour_discount(departure.tour, seasonal.get(country.slug, 0))
        country.departure_count += 1
        country.available_count += int(departure.available)
        if departure.available:
            country.available_tours.add(departure.tour_id)
        country.booked_travelers += departure.booked_travelers
        if not selected or departure.tour.country == selected:
            departures.append(departure)
    for country in countries:
        country.available_tour_count = len(country.available_tours)
    groups = OrderedDict()
    for departure in departures:
        groups.setdefault(departure.start_date.replace(day=1), []).append(departure)
    if selected:
        tours = tours.filter(country=selected)
    return {'countries': countries, 'catalogue_countries': countries, 'selected_country': selected,
        'selected_country_record': selected_record, 'country_picker': not selected,
        'selected_year': year, 'years': sorted(value for value in years if value is not None), 'search_q': query, 'selected_month': month,
        'departure_groups': list(groups.items()), 'departure_count': len(departures), 'tours': tours,
        'search_start_date': request.GET.get('start_date', ''), 'search_end_date': request.GET.get('end_date', ''), 'start_date_filter': request.GET.get('start_date', ''), 'end_date_filter': request.GET.get('end_date', '')}


def home(request):
    data = catalogue_data(request)
    stories = BlogPost.objects.filter(region__is_active=True)
    if data['selected_country']:
        stories = stories.filter(country=data['selected_country'])
    return render(request, 'home.html', {**data, 'home_catalogue': True, 'stories': stories.order_by('-created_at')[:3]})


def tours(request):
    return render(request, 'tour_catalogue.html', catalogue_data(request))


def travel_stories(request):
    data = catalogue_data(request, stories=True)
    posts = BlogPost.objects.filter(region__is_active=True).select_related('region')
    if data['selected_country']:
        posts = posts.filter(country=data['selected_country'])
    if data['selected_year']:
        posts = posts.filter(created_at__year=data['selected_year'])
    if data['search_q']:
        posts = posts.filter(Q(title__icontains=data['search_q']) | Q(content__icontains=data['search_q']))
    moments = BlogImage.objects.filter(post__in=posts).select_related('post').order_by('-post__created_at', 'pk')[:18]
    return render(request, 'blog_list.html', {**data, 'story_catalogue': True, 'posts': posts.order_by('-created_at'), 'moments': moments})
