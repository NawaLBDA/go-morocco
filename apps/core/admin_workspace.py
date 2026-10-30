"""Persistent staff content context, independent of public country visibility."""
from django.apps import apps
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from .models import Country

SESSION_KEY = 'admin_workspace_country'


def selected_country(request):
    if not getattr(getattr(request, 'user', None), 'is_staff', False):
        return None
    slug = getattr(request, 'session', {}).get(SESSION_KEY)
    return Country.objects.filter(slug=slug).first() if slug else None


def reservation_country(request):
    slug = request.GET.get('country') or getattr(request, 'site_country', None)
    if slug:
        country = get_object_or_404(Country, slug=slug)
        request.session[SESSION_KEY] = country.slug
        return country
    country = selected_country(request) or Country.objects.filter(slug='morocco').first() or Country.objects.first()
    if not country:
        raise Http404('Create a country first.')
    request.session[SESSION_KEY] = country.slug
    return country


@staff_member_required
@require_POST
def select_country(request):
    slug = request.POST.get('country', '')
    if slug:
        request.session[SESSION_KEY] = get_object_or_404(Country, slug=slug).slug
    else:
        request.session.pop(SESSION_KEY, None)
    return redirect('admin:index')


def workspace_context(request):
    if not getattr(getattr(request, 'user', None), 'is_staff', False):
        return {}
    country = selected_country(request)
    links = []
    for model, label in [
        ('tour', 'Tours and packages'), ('tourdeparture', 'Departure dates'),
        ('destination', 'Destinations'), ('guide', 'Guides and teams'),
        ('reservation', 'Reservations'), ('waitlistentry', 'Waiting list'),
        ('blogpost', 'Travel stories'), ('promotion', 'Promotions'),
        ('countrycontent', 'Country page'), ('section', 'Page sections'),
        ('information', 'Practical information'), ('contactmessage', 'Contact messages'),
        ('contactemailsettings', 'Contact email settings'),
        ('bookingnotificationsettings', 'Booking notification settings'),
        ('bookingnotification', 'Notification delivery logs'),
    ]:
        if admin.site.is_registered(apps.get_model('core', model)) and (request.user.has_perm(f'core.view_{model}') or request.user.has_perm(f'core.change_{model}')):
            links.append({'label': label, 'url': reverse(f'admin:core_{model}_changelist')})
    return {'admin_workspace_country': country, 'admin_workspace_countries': Country.objects.all(),
        'admin_workspace_links': links}
